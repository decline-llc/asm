"""OS-owned file leases, released automatically when a process exits."""
import os
import threading
import time
from pathlib import Path


class LeaseBusy(ValueError):
    pass


class FileLease:
    def __init__(self, path, *, timeout=0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    self.file.close()
                    self.file = None
                    raise LeaseBusy("Another process owns this run or state transaction") from None
                time.sleep(0.02)

    def close(self):
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class SharedStateLock:
    """Reentrant inside one store, exclusive across stores and processes."""
    def __init__(self, path):
        self.path = path
        self.thread_lock = threading.RLock()
        self.local = threading.local()

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            depth = getattr(self.local, "depth", 0)
            if depth == 0:
                self.local.lease = FileLease(self.path, timeout=30)
            self.local.depth = depth + 1
        except BaseException:
            self.thread_lock.release()
            raise
        return self

    def __exit__(self, *_):
        try:
            self.local.depth -= 1
            if self.local.depth == 0:
                self.local.lease.close()
        finally:
            self.thread_lock.release()
