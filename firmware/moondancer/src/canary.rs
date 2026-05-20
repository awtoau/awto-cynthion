// Stack overflow detection via canary word and current-SP stack usage.
//
// The canary is written at `_sheap` (first address above BSS, below the stack
// gap). If the stack grows down past this address the canary is clobbered and
// `is_intact()` returns false. Detected on every MachineExternal entry.
//
// See issue #14.

const CANARY_VALUE: u32 = 0xDEAD_C0DE;

extern "C" {
    static _sheap: u8;        // bottom of free space = top of BSS (riscv-rt)
    static _stack_start: u8;  // top of blockram = initial SP
}

/// Write canary at `_sheap`. Call once during init before any significant
/// stack usage (i.e. in `pre_main` or at the top of `main`).
pub unsafe fn init() {
    let addr = core::ptr::addr_of!(_sheap) as *mut u32;
    core::ptr::write_volatile(addr, CANARY_VALUE);
}

/// Returns true if the canary word at `_sheap` is intact.
pub unsafe fn is_intact() -> bool {
    let addr = core::ptr::addr_of!(_sheap) as *const u32;
    core::ptr::read_volatile(addr) == CANARY_VALUE
}

/// Read the raw canary word (for diagnostics / selftest reporting).
pub unsafe fn read_raw() -> u32 {
    let addr = core::ptr::addr_of!(_sheap) as *const u32;
    core::ptr::read_volatile(addr)
}

/// Overwrite the canary with zero — for fault-injection testing only.
/// The panic fires at the next MachineExternal interrupt.
pub unsafe fn corrupt() {
    let addr = core::ptr::addr_of!(_sheap) as *mut u32;
    core::ptr::write_volatile(addr, 0);
}

/// Bytes of stack consumed from the top: distance from current SP down
/// to `_stack_start`. Read at interrupt entry — reflects interrupt-path depth.
pub fn stack_used_bytes() -> u32 {
    let sp: usize;
    unsafe { core::arch::asm!("mv {}, sp", out(reg) sp) }
    let top = core::ptr::addr_of!(_stack_start) as usize;
    top.saturating_sub(sp) as u32
}

/// Total stack space available (blockram top - sheap).
pub fn stack_total_bytes() -> u32 {
    let top = core::ptr::addr_of!(_stack_start) as usize;
    let bottom = core::ptr::addr_of!(_sheap) as usize;
    top.saturating_sub(bottom) as u32
}
