"""Unit tests for the content-addressed kernel compilation cache.

These tests exercise the vendored artiq compiler (vendor/artiq), which is not
on sys.path in a plain ``nix develop -c pytest`` run; run them via the wrapper
that injects the vendored paths:

    nix develop -c python scripts/pytest_vendored.py tests/test_kernel_cache.py -v

In a plain run (system artiq without artiq.compiler.kernel_cache) they skip.
"""

import functools
import json

import pytest

kernel_cache = pytest.importorskip(
    "artiq.compiler.kernel_cache",
    reason="requires vendored artiq (run via scripts/pytest_vendored.py)",
)

import pythonparser  # noqa: E402
from artiq.compiler import module as compiler_module  # noqa: E402
from artiq.compiler.module import Module  # noqa: E402
from artiq.compiler.module import Source
from artiq.compiler.targets import RV32GTarget  # noqa: E402


@pytest.fixture(autouse=True)
def _parse_as_py36(monkeypatch):
    # pythonparser's lexer does not know the running interpreter's grammar
    # version; the kernel embedding path pins (3, 6) (see Stitcher), but the
    # Source testbench path used here relies on the default. Pin it likewise.
    monkeypatch.setattr(
        compiler_module,
        "parse_buffer",
        functools.partial(pythonparser.parse_buffer, version=(3, 6)),
    )


SOURCE_A = """
def entrypoint():
    x = 0
    for i in range(10):
        x += i
    return x
"""

SOURCE_B = """
def entrypoint():
    x = 1.0
    while x < 100.0:
        x *= 2.0
    return x
"""

# Same code structure as SOURCE_A but a different embedded constant, i.e. the
# moral equivalent of recompiling with a different parameter value.
SOURCE_A_OTHER_VALUE = SOURCE_A.replace("range(10)", "range(20)")


def build_ir(source_text):
    """Build textual LLVM IR for a source string on a fresh target."""
    target = RV32GTarget()
    module = Module(Source.from_string(source_text))
    return target, target.build_llvm_ir(module)


def compile_source(source_text):
    target = RV32GTarget()
    module = Module(Source.from_string(source_text))
    return target.compile_and_link([module])


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    path = tmp_path / "kernel_cache"
    monkeypatch.setenv("ARTIQ_KERNEL_CACHE_DIR", str(path))
    monkeypatch.delenv("ARTIQ_KERNEL_CACHE", raising=False)
    return path


def count_assemble_calls(monkeypatch):
    calls = []
    original = RV32GTarget.assemble

    def counting_assemble(self, llmodule):
        calls.append(llmodule)
        return original(self, llmodule)

    monkeypatch.setattr(RV32GTarget, "assemble", counting_assemble)
    return calls


def test_same_code_same_hash():
    target1, ir1 = build_ir(SOURCE_A)
    target2, ir2 = build_ir(SOURCE_A)
    assert target1.compute_code_hash([ir1]) == target2.compute_code_hash([ir2])


def test_different_code_different_hash():
    target1, ir1 = build_ir(SOURCE_A)
    target2, ir2 = build_ir(SOURCE_B)
    assert target1.compute_code_hash([ir1]) != target2.compute_code_hash([ir2])


def test_different_values_different_hash():
    # Until parameter values are uploaded separately (phase B), a changed
    # embedded value must be a cache miss, not a stale hit.
    target1, ir1 = build_ir(SOURCE_A)
    target2, ir2 = build_ir(SOURCE_A_OTHER_VALUE)
    assert target1.compute_code_hash([ir1]) != target2.compute_code_hash([ir2])


def test_cache_hit_skips_compilation(cache_dir, monkeypatch):
    calls = count_assemble_calls(monkeypatch)

    library_first = compile_source(SOURCE_A)
    assert len(calls) == 1
    elf_files = list(cache_dir.glob("*.elf"))
    assert len(elf_files) == 1

    library_second = compile_source(SOURCE_A)
    assert len(calls) == 1, "cache hit must skip assembly"
    assert library_second == library_first

    library_third = compile_source(SOURCE_B)
    assert len(calls) == 2, "different code must recompile"
    assert library_third != library_first


def test_cache_disabled(cache_dir, monkeypatch):
    monkeypatch.setenv("ARTIQ_KERNEL_CACHE", "0")
    calls = count_assemble_calls(monkeypatch)

    compile_source(SOURCE_A)
    compile_source(SOURCE_A)
    assert len(calls) == 2, "disabled cache must always compile"
    assert not cache_dir.exists()


def test_environment_fingerprint_invalidates(cache_dir, monkeypatch):
    calls = count_assemble_calls(monkeypatch)

    compile_source(SOURCE_A)
    assert len(calls) == 1

    # Simulate a compiler/environment change (e.g. edited vendored sources).
    monkeypatch.setattr(kernel_cache, "_fingerprint", b"different fingerprint")
    compile_source(SOURCE_A)
    assert len(calls) == 2, "changed environment must invalidate the cache"


def test_metadata_written(cache_dir):
    compile_source(SOURCE_A)
    meta_files = list(cache_dir.glob("*.json"))
    assert len(meta_files) == 1
    metadata = json.loads(meta_files[0].read_text())
    assert metadata["format"] == kernel_cache.CACHE_FORMAT_VERSION
    assert metadata["artiq_commit"] == kernel_cache.artiq_commit()
    assert metadata["triple"] == RV32GTarget.triple
    assert metadata["elf_size"] > 0
    assert meta_files[0].stem == metadata["code_hash"]


def test_set_parameter_values():
    from artiq.coredevice.core import Core

    class Holder:
        frequency = 1e6

    holder = Holder()
    # set_parameter_values only touches host attributes, so an unbuilt Core
    # class is not needed; call the unbound method directly.
    Core.set_parameter_values(object(), holder, frequency=2e6)
    assert holder.frequency == 2e6

    with pytest.raises(AttributeError):
        Core.set_parameter_values(object(), holder, frequenzy=3e6)
