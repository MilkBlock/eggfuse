//! Synchronous native Metal exchange. The GPU and CPU share one output bank.
use crate::program::Result;
use std::{
    ffi::{CString, c_char, c_void},
    ptr::NonNull,
};

unsafe extern "C" {
    fn cell_gpu_open(code: *const c_char) -> *mut c_void;
    fn cell_gpu_close(p: *mut c_void);
    fn cell_gpu_match(
        p: *mut c_void,
        left: *const i32,
        nl: usize,
        right: *const i32,
        nr: usize,
        checks: *const i32,
        nt: usize,
        shape: *const i32,
        width: i32,
        result: *mut [i32; 2],
        gpu: *mut f64,
    ) -> i32;
}
pub(super) struct Native(NonNull<c_void>);
impl Drop for Native {
    fn drop(&mut self) {
        unsafe { cell_gpu_close(self.0.as_ptr()) }
    }
}
impl Native {
    pub(super) fn new() -> Result<Self> {
        let src = CString::new(include_str!("gpu_bindings.metal")).unwrap();
        NonNull::new(unsafe { cell_gpu_open(src.as_ptr()) })
            .map(Self)
            .ok_or("cannot initialize the Metal binding pipeline".into())
    }
    pub(super) fn query(
        &self,
        data: &[Vec<i32>],
        widths: &[usize],
        checks: &[i32],
    ) -> Result<(Vec<[usize; 2]>, f64, u64, u64)> {
        let left = data[0].len() / widths[0];
        let right = data[1].len() / widths[1];
        let pairs = left
            .checked_mul(right)
            .filter(|&v| v <= i32::MAX as usize)
            .ok_or("GPU pair address overflow")?;
        self.dispatch(
            data,
            checks,
            pairs,
            [
                left as i32,
                right as i32,
                widths[0] as i32,
                widths[1] as i32,
                (checks.len() / 2) as i32,
                0,
            ],
        )
    }
    pub(super) fn dispatch(
        &self,
        data: &[Vec<i32>],
        checks: &[i32],
        pairs: usize,
        mut shape: [i32; 6],
    ) -> Result<(Vec<[usize; 2]>, f64, u64, u64)> {
        let mut received = Vec::new();
        let mut gpu_seconds = 0.0;
        let mut traffic = 0;
        let mut output = vec![[0i32; 2]; pairs.min(65536)];
        for offset in (0..pairs).step_by(65536) {
            let width = (pairs - offset).min(65536);
            shape[5] = offset as i32;
            let mut gpu = 0.;
            // Input and output lifetimes cover the blocking command. No raw pointer is retained.
            let count = unsafe {
                cell_gpu_match(
                    self.0.as_ptr(),
                    data[0].as_ptr(),
                    data[0].len(),
                    data[1].as_ptr(),
                    data[1].len(),
                    checks.as_ptr(),
                    checks.len(),
                    shape.as_ptr(),
                    width as i32,
                    output.as_mut_ptr(),
                    &mut gpu,
                )
            };
            if count < 0 || count as usize > width {
                return Err("Metal binding dispatch failed".into());
            }
            received.extend(
                output[..count as usize]
                    .iter()
                    .map(|&[a, b]| [a as usize, b as usize]),
            );
            traffic += 4 * (data[0].len() + data[1].len() + checks.len() + shape.len() + 1) as u64;
            gpu_seconds += gpu;
        }
        let bytes = 8 * received.len() as u64;
        Ok((received, gpu_seconds, traffic, bytes))
    }
}

#[cfg(test)]
mod tests {
    use super::Native;

    #[test]
    fn shared_shader_preserves_fresh_nonpivot_and_run_group_identity() {
        let device = Native::new().unwrap();
        // Header -1 hides a row, 0 is stale, 1 is fresh. Match both columns
        // for equality, including repeated keys in different source rows.
        let data = [vec![0, 7, -1, 7, 1, 8, 0, 9], vec![1, 7, 0, 8, 0, 9]];
        let (mut pair, ..) = device.query(&data, &[2, 2], &[1, 3]).unwrap();
        pair.sort_unstable();
        assert_eq!(pair, vec![[0, 0], [2, 1]]);
        // Rule 0 matches equality; rule 1 accepts only literal 8 in both
        // rows. Their inputs can share buffers but their output owners differ.
        let directory = [
            12, 0, 0, 3, 2, 2, 16, 1, 24, 0, 0, 3, 2, 2, 18, 2, 1, 3, 1, -9, 3, -9,
        ];
        let (mut tokens, ..) = device
            .dispatch(&data, &directory, 24, [-2, 0, 0, 0, 0, 0])
            .unwrap();
        tokens.sort_unstable();
        assert_eq!(tokens, vec![[0, 0], [0, 7], [1, 7]]);
    }
}
