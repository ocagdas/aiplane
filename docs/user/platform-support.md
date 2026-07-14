# Platform support

Aiplane separates portable inspection/configuration features from host-mutating helpers. Unsupported operations fail with `name: unsupported_platform`; this is distinct from a supported operation whose required executable is missing.

| Capability | Ubuntu/Debian Linux | Other Linux | WSL2 | macOS | Windows |
|---|---|---|---|---|---|
| Install/run the Python CLI | Supported | Supported | Supported | Supported | Supported |
| Profile validation, policy, recommendation, and exports | Supported | Supported | Supported | Supported | Supported |
| Generic runtime/endpoint/tool detection | Supported | Supported | Supported | Supported | Supported |
| Linux procfs, `lspci`, ROCm, and Linux GPU discovery probes | Supported | Supported where tools exist | Inspection only | Skipped | Skipped |
| Helper-managed runtime install/update | Supported | Unsupported; use vendor installer | Unsupported; use vendor installer inside the chosen WSL/native boundary | Unsupported; use vendor installer | Unsupported; use vendor installer |
| Bash repository setup helper | Supported | Best effort, not a promised mutation path | Best effort for development | Not a platform-native installer | Not a platform-native installer |
| SSH tunnel planning | Supported | Supported | Supported | Supported | Supported when OpenSSH is available |
| SSH tunnel lifecycle (`status`/`start`/`stop`) | Supported | Supported POSIX path | Supported with normal WSL process caveats | Supported through POSIX process identity | Unsupported; returns `unsupported_platform` before process or state access |

WSL policy: read-only inspection, profile operations, planning, and exports are supported. Aiplane does not assume that a runtime, GPU driver, Docker daemon, or endpoint installed on Windows is visible inside WSL, or vice versa. Runtime mutation helpers therefore remain disabled on WSL; use the vendor-native installer in the environment that owns the runtime.

Hardware discovery reports a `platform_support` block. On non-Linux systems it does not execute Linux procfs, PCI, ROCm, or Linux-oriented GPU probes and explains the skipped coverage in `notes`. This means an unknown GPU is not the same as a confirmed absence of GPUs.

The platform matrix is a behavior contract, not a claim that every upstream runtime supports every operating system. Runtime/vendor requirements still apply.
