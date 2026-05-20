use libgreat::error::{GreatError, GreatResult};
use libgreat::gcp::{self, Verb};

use log::debug;
use zerocopy::{FromBytes, FromZeroes, LittleEndian, Unaligned, U32};

use core::any::Any;

pub static CLASS: gcp::Class = gcp::Class {
    id: gcp::ClassId::selftest,
    name: "selftest",
    docs: CLASS_DOCS,
    verbs: &VERBS,
};

pub static CLASS_DOCS: &str = "Provides functionality for a Cynthion to self-test itself.\0";

/// Fields are `"\0"`  where C implementation has `""`
/// Fields are `"*\0"` where C implementation has `NULL`
pub static VERBS: [Verb; 5] = [
    Verb {
        id: 0x00,
        name: "get_canary_status\0",
        doc: "Returns canary word at _sheap, stack bytes used, stack bytes total.\0",
        in_signature: "\0",
        in_param_names: "*\0",
        out_signature: "<III\0",
        out_param_names: "canary_value, stack_used, stack_total\0",
    },
    Verb {
        id: 0x10,
        name: "test_error_return_code\0",
        doc: "\0",
        in_signature: "<I\0",
        in_param_names: "code\0",
        out_signature: "<S\0",
        out_param_names: "result\0",
    },
    Verb {
        id: 0x11,
        name: "trigger_panic\0",
        doc: "Deliberately panics the firmware. Device will hang until power-cycled.\0",
        in_signature: "\0",
        in_param_names: "*\0",
        out_signature: "\0",
        out_param_names: "*\0",
    },
    Verb {
        id: 0x12,
        name: "trigger_stack_overflow\0",
        doc: "Overflows the stack via unbounded recursion. Canary fires on next interrupt.\0",
        in_signature: "\0",
        in_param_names: "*\0",
        out_signature: "\0",
        out_param_names: "*\0",
    },
    Verb {
        id: 0x13,
        name: "corrupt_canary\0",
        doc: "Overwrites the stack canary word. Panic fires on next MachineExternal interrupt.\0",
        in_signature: "\0",
        in_param_names: "*\0",
        out_signature: "\0",
        out_param_names: "*\0",
    },
];

// - verb implementations -----------------------------------------------------

pub fn get_canary_status<'a>(
    _arguments: &[u8],
    _context: &'a dyn Any,
) -> GreatResult<impl Iterator<Item = u8> + 'a> {
    let canary_value = unsafe { crate::canary::read_raw() };
    let stack_used = crate::canary::stack_used_bytes();
    let stack_total = crate::canary::stack_total_bytes();
    debug!("  get_canary_status: canary=0x{:08x} used={} total={}", canary_value, stack_used, stack_total);
    let response = canary_value.to_le_bytes().into_iter()
        .chain(stack_used.to_le_bytes())
        .chain(stack_total.to_le_bytes());
    Ok(response)
}

pub fn test_error_return_code<'a>(
    arguments: &[u8],
    _context: &'a dyn Any,
) -> GreatResult<impl Iterator<Item = u8> + 'a> {
    #[repr(C)]
    #[derive(FromBytes, FromZeroes, Unaligned)]
    struct Args {
        code: U32<LittleEndian>,
    }
    let args = Args::read_from(arguments).ok_or(GreatError::InvalidArgument)?;

    match args.code.into() {
        0_u32 => {
            let s = "ok";
            debug!("  test_error_return_code -> 0 -> Ok('ok')");
            Ok(s.as_bytes().iter().copied())
        }
        code => {
            let code: GreatError = unsafe { core::mem::transmute(code) };
            debug!("  test_error_return_code -> {} -> Err({})", args.code, code);
            Err(code)
        }
    }
}

pub fn trigger_panic<'a>(
    _arguments: &[u8],
    _context: &'a dyn Any,
) -> GreatResult<impl Iterator<Item = u8> + 'a> {
    panic!("deliberate test panic via selftest::trigger_panic");
    #[allow(unreachable_code)]
    Ok([].into_iter())
}

/// Unbounded recursion to overflow the stack. Each frame is at least 16 bytes
/// (saved ra + s0 + locals). The volatile read prevents tail-call elimination.
#[inline(never)]
fn recurse(depth: u32) -> u32 {
    let here = depth;
    let _ = unsafe { core::ptr::read_volatile(&here) };
    recurse(depth.wrapping_add(1))
}

pub fn trigger_stack_overflow<'a>(
    _arguments: &[u8],
    _context: &'a dyn Any,
) -> GreatResult<impl Iterator<Item = u8> + 'a> {
    let _ = recurse(0);
    Ok([].into_iter())
}

pub fn corrupt_canary<'a>(
    _arguments: &[u8],
    _context: &'a dyn Any,
) -> GreatResult<impl Iterator<Item = u8> + 'a> {
    // Overwrite canary with zero and return normally. The panic fires at the
    // next MachineExternal interrupt (~1 ms). Lets the GCP response reach the
    // host first, making this the observable/testable path for canary detection.
    unsafe { crate::canary::corrupt() };
    debug!("  corrupt_canary: canary overwritten — panic expected on next interrupt");
    Ok([].into_iter())
}

// - dispatch -----------------------------------------------------------------

use libgreat::gcp::{iter_to_response, GreatResponse, LIBGREAT_MAX_COMMAND_SIZE};

pub fn dispatch(
    verb_number: u32,
    arguments: &[u8],
    response_buffer: [u8; LIBGREAT_MAX_COMMAND_SIZE],
) -> GreatResult<GreatResponse> {
    let no_context: Option<u8> = None;

    match verb_number {
        0x00 => {
            let iter = get_canary_status(arguments, &no_context)?;
            let response = iter_to_response(iter, response_buffer);
            Ok(response)
        }
        0x10 => {
            let iter = test_error_return_code(arguments, &no_context)?;
            let response = iter_to_response(iter, response_buffer);
            Ok(response)
        }
        0x11 => {
            let iter = trigger_panic(arguments, &no_context)?;
            let response = iter_to_response(iter, response_buffer);
            Ok(response)
        }
        0x12 => {
            let iter = trigger_stack_overflow(arguments, &no_context)?;
            let response = iter_to_response(iter, response_buffer);
            Ok(response)
        }
        0x13 => {
            let iter = corrupt_canary(arguments, &no_context)?;
            let response = iter_to_response(iter, response_buffer);
            Ok(response)
        }

        _verb_number => Err(GreatError::InvalidArgument),
    }
}
