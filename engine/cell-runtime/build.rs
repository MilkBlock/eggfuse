use std::{env, path::PathBuf, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=src/gpu_bindings.m");
    if env::var_os("CARGO_FEATURE_GPU_BINDINGS").is_none()
        || env::var("CARGO_CFG_TARGET_OS").unwrap() != "macos"
    {
        return;
    }
    let dir = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let object = dir.join("bindings.o");
    assert!(
        Command::new("xcrun")
            .args([
                "--sdk",
                "macosx",
                "clang",
                "-O3",
                "-fobjc-arc",
                "-c",
                "src/gpu_bindings.m",
                "-o"
            ])
            .arg(&object)
            .status()
            .unwrap()
            .success()
    );
    assert!(
        Command::new("ar")
            .arg("rcs")
            .arg(dir.join("libcell_binding_gpu.a"))
            .arg(object)
            .status()
            .unwrap()
            .success()
    );
    println!("cargo:rustc-link-search=native={}", dir.display());
    println!("cargo:rustc-link-lib=static=cell_binding_gpu");
    println!("cargo:rustc-link-lib=framework=Foundation");
    println!("cargo:rustc-link-lib=framework=Metal");
    println!("cargo:rustc-link-lib=dylib=objc");
}
