"""
Content-addressed cache for compiled and linked kernel binaries.

Host state (attribute values, embedded constants) is materialized as global
initializers during LLVM IR generation, so the textual LLVM IR fully
determines the linked output for a given compiler environment. The cache key
is therefore a hash of the generated LLVM IR plus an environment fingerprint
(compiler sources, llvmlite/LLVM version, target description), which makes
stale hits impossible: any change to the compiler, the kernel code, the type
structure or the embedded values changes the key.

Cache layout (one pair of files per entry)::

    {root}/{code_hash}.elf    linked shared library, as returned by Target.link
    {root}/{code_hash}.json   metadata (artiq commit, target, creation time)

Environment variables::

    ARTIQ_KERNEL_CACHE=0      disable the cache entirely
    ARTIQ_KERNEL_CACHE_DIR    cache directory (default: ./.artiq_kernel_cache)

Cache failures (unreadable directory, corrupt entry, full disk) are never
fatal; the compiler falls back to a normal compile.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

CACHE_FORMAT_VERSION = 1

_fingerprint = None
_artiq_commit = None


def _package_root():
    """Root of the artiq package (the directory containing ``compiler/``)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def artiq_commit():
    """Git commit of the artiq tree this module was loaded from, or the
    package version if it is not a git checkout."""
    global _artiq_commit
    if _artiq_commit is None:
        try:
            _artiq_commit = subprocess.check_output(
                ["git", "-C", _package_root(), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL).decode().strip()
        except (OSError, subprocess.CalledProcessError):
            try:
                from artiq import __version__
                _artiq_commit = __version__
            except ImportError:
                _artiq_commit = "unknown"
    return _artiq_commit


def _compiler_sources_digest():
    """Hash of all compiler sources (including the linker script).

    The vendored compiler tree is routinely edited without committing, so the
    git commit alone is not a sufficient invalidation key; this digest tracks
    the actual content that determines compiler output.
    """
    compiler_dir = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.blake2b(digest_size=16)
    for dirpath, dirnames, filenames in sorted(os.walk(compiler_dir)):
        dirnames.sort()
        for filename in sorted(filenames):
            if not filename.endswith((".py", ".ld")):
                continue
            path = os.path.join(dirpath, filename)
            h.update(os.path.relpath(path, compiler_dir).encode())
            h.update(b"\0")
            with open(path, "rb") as f:
                h.update(f.read())
            h.update(b"\0")
    return h.digest()


def environment_fingerprint():
    """Digest of everything outside the LLVM IR that affects the binary."""
    global _fingerprint
    if _fingerprint is None:
        h = hashlib.blake2b(digest_size=16)
        h.update(b"format:%d\0" % CACHE_FORMAT_VERSION)
        h.update(artiq_commit().encode() + b"\0")
        h.update(_compiler_sources_digest() + b"\0")
        try:
            import llvmlite
            from llvmlite import binding as llvm
            h.update(llvmlite.__version__.encode() + b"\0")
            h.update(repr(llvm.llvm_version_info).encode() + b"\0")
        except ImportError:
            pass
        _fingerprint = h.digest()
    return _fingerprint


class KernelCache:
    def __init__(self, root):
        self.root = os.path.abspath(root)

    @classmethod
    def from_env(cls):
        """Return the configured cache, or None if caching is disabled."""
        if os.getenv("ARTIQ_KERNEL_CACHE", "1").lower() in ("0", "off", "false", ""):
            return None
        root = os.getenv("ARTIQ_KERNEL_CACHE_DIR") or ".artiq_kernel_cache"
        return cls(root)

    def _entry_paths(self, code_hash):
        return (os.path.join(self.root, code_hash + ".elf"),
                os.path.join(self.root, code_hash + ".json"))

    def get(self, code_hash):
        """Return the cached library for ``code_hash``, or None."""
        elf_path, _ = self._entry_paths(code_hash)
        try:
            with open(elf_path, "rb") as f:
                library = f.read()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("kernel cache read failed for %s: %s", elf_path, exc)
            return None
        try:
            # Keep mtime fresh so a future pruning policy can evict LRU entries.
            os.utime(elf_path)
        except OSError:
            pass
        return library

    def put(self, code_hash, library, metadata=None):
        """Store a linked library under ``code_hash``. Never raises."""
        elf_path, meta_path = self._entry_paths(code_hash)
        entry_metadata = {
            "format": CACHE_FORMAT_VERSION,
            "code_hash": code_hash,
            "artiq_commit": artiq_commit(),
            "cache_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elf_size": len(library),
        }
        if metadata:
            entry_metadata.update(metadata)
        try:
            os.makedirs(self.root, exist_ok=True)
            self._write_atomic(elf_path, library)
            self._write_atomic(meta_path,
                               json.dumps(entry_metadata, indent=1).encode())
        except OSError as exc:
            logger.warning("kernel cache write failed for %s: %s", elf_path, exc)

    def _write_atomic(self, path, data):
        fd, tmp_path = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
