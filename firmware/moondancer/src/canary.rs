// Stack overflow detection via canary word and current-SP stack usage.
//
// The canary is written at `_sheap` (first address above BSS, below the stack
// gap). If the stack grows down past this address the canary is clobbered and
// `is_intact()` returns false. Detected on every MachineExternal entry.
//
// See issue #14.

// `_sheap` is a linker symbol declared `u8` (the usual way to name an extern
// symbol whose address is what matters). riscv-rt word-aligns it, so casting
// its address to *u32 is sound; clippy's alignment lint cannot see that.
#![allow(clippy::cast_ptr_alignment)]

const CANARY_VALUE: u32 = 0xDEAD_C0DE;

extern "C" {
    static _sheap: u8;        // bottom of free space = top of BSS (riscv-rt)
    static _stack_start: u8;  // top of blockram = initial SP
}

/// Write canary at `_sheap`. Call once during init before any significant
/// stack usage (i.e. in `pre_main` or at the top of `main`).
///
/// # Safety
///
/// Writes one word at `_sheap`. The caller must ensure nothing else owns that
/// address — in practice it is the base of the heap region, unused here.
pub unsafe fn init() {
    let addr = core::ptr::addr_of!(_sheap) as *mut u32;
    core::ptr::write_volatile(addr, CANARY_VALUE);
}

/// Returns true if the canary word at `_sheap` is intact.
///
/// # Safety
///
/// Reads one word at `_sheap`. Sound once [`init`] has run; before that the
/// value is whatever the region happened to contain.
#[must_use]
pub unsafe fn is_intact() -> bool {
    let addr = core::ptr::addr_of!(_sheap).cast::<u32>();
    core::ptr::read_volatile(addr) == CANARY_VALUE
}

/// Read the raw canary word (for diagnostics / selftest reporting).
///
/// # Safety
///
/// Reads one word at `_sheap`; see [`is_intact`].
#[must_use]
pub unsafe fn read_raw() -> u32 {
    let addr = core::ptr::addr_of!(_sheap).cast::<u32>();
    core::ptr::read_volatile(addr)
}

/// Overwrite the canary with zero — for fault-injection testing only.
/// The panic fires at the next `MachineExternal` interrupt.
///
/// # Safety
///
/// Deliberately breaks the invariant [`is_intact`] checks, so the next
/// interrupt entry panics. Test builds only.
pub unsafe fn corrupt() {
    let addr = core::ptr::addr_of!(_sheap) as *mut u32;
    core::ptr::write_volatile(addr, 0);
}

/// Bytes of stack consumed from the top: distance from current SP down
/// to `_stack_start`. Read at interrupt entry — reflects interrupt-path depth.
#[must_use]
pub fn stack_used_bytes() -> u32 {
    let sp: usize;
    unsafe { core::arch::asm!("mv {}, sp", out(reg) sp) }
    let top = core::ptr::addr_of!(_stack_start) as usize;
    top.saturating_sub(sp) as u32
}

/// Total stack space available (blockram top - sheap).
#[must_use]
pub fn stack_total_bytes() -> u32 {
    let top = core::ptr::addr_of!(_stack_start) as usize;
    let bottom = core::ptr::addr_of!(_sheap) as usize;
    top.saturating_sub(bottom) as u32
}
