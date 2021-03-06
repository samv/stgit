# Run the test suite in parallel.

import glob
import itertools as it
import math
import optparse
import os
import os.path
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback

# Number of jobs to run in parallel.
def default_num_jobs():
    try:
        # One job per processor should be about right.
        import multiprocessing
        return 2 * multiprocessing.cpu_count()
    except ImportError:
        # Couldn't determine number of processors (probably because
        # Python version is < 2.6); use a conservative fallback.
        return 4

class TestQueue(object):
    def __init__(self, tests, cleanup):

        def cleanup_jobs(top_dirs):
            for td in top_dirs:
                for e in os.listdir(td):
                    yield os.path.join(td, e)

        self.__remaining = sorted(tests, reverse=True)
        self.__running = set()
        self.__success = set()
        self.__fail = set()
        self.__clean_jobs = set(cleanup)
        self.__clean_todo = set(cleanup_jobs(self.__clean_jobs))
        self.__clean_running = set()
        self.__clean_done = set()
        self.lock = threading.Lock()
        self.__cv = threading.Condition(self.lock)
    def __iter__(self):
        return self

    # True if all jobs have completed.
    def __done(self):
        # Called with self.lock held.
        return (not self.__remaining and not self.__running
                and not len(self.__clean_todo) and not self.__clean_running)

    # Make progress report, and check if we're all done.
    def __report(self):
        # Called with self.lock held.
        cd = len(self.__clean_done) + 1e-3  # clever way to avoid div by zero
        cr = len(self.__clean_running)
        ct = len(self.__clean_todo)
        sys.stdout.write(("\rQueue: %3d,  Running: %3d,  OK: %3d,"
                          "  Failed: %3d,  Cleanup: %3d%%")
                         % (len(self.__remaining), len(self.__running),
                            len(self.__success), len(self.__fail),
                            math.floor(100.0 * cd / (cd + cr + ct))))
        sys.stdout.flush()
        if self.__done():
            sys.stdout.write("\n")
            self.__cv.notifyAll()

    # Yield free jobs until none are left.
    def next(self):
        with self.lock:
            if not self.__remaining:
                raise StopIteration
            t = self.__remaining.pop()
            self.__running.add(t)
            self.__report()
            return t

    # Report that a job has completed.
    def finished(self, t, success):
        with self.lock:
            self.__running.remove(t)
            (self.__success if success else self.__fail).add(t)
            self.__report()

    # Yield free cleaning jobs until none are left.
    def cleaning_jobs(self):
        while True:
            with self.lock:
                if not self.__clean_todo:
                    return
                c = self.__clean_todo.pop()
                self.__clean_running.add(c)
            yield c

    # Report that a cleaning job has completed.
    def deleted(self, c):
        with self.lock:
            self.__clean_running.remove(c)
            self.__clean_done.add(c)
            self.__report()

    # Wait for all jobs to complete.
    def wait(self):
        with self.lock:
            while not self.__done():
                self.__cv.wait()
            for c in self.__clean_jobs:
                os.rmdir(c)
            return set(self.__fail)

def start_worker(q):
    def w():
        for t in q:
            try:
                ok = False  # assume the worst until proven otherwise
                s = os.path.join("trash", t)
                e = dict(os.environ)
                e["SCRATCHDIR"] = s
                p = subprocess.Popen([os.path.join(os.getcwd(), t), "-v"],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,
                                     env=e)
                (out, err) = p.communicate()
                assert err is None
                with open(os.path.join(s, "output"), "w") as f:
                    f.write(out)
                    f.write("\nExited with code %d\n" % p.returncode)
                if p.returncode == 0:
                    ok = True
            except:
                # Log the traceback. Use the mutex so that we
                # won't write multiple tracebacks to stderr at the
                # same time.
                with q.lock:
                    traceback.print_exc()
            finally:
                q.finished(t, ok)
    threading.Thread(target=w).start()

def start_cleaner(q):
    def w():
        for c in q.cleaning_jobs():
            try:
                (shutil.rmtree if os.path.isdir(c) else os.remove)(c)
            finally:
                q.deleted(c)
    threading.Thread(target=w).start()

def main():
    p = optparse.OptionParser()
    p.add_option("-j", "--jobs", type="int",
                 help="number of tests to run in parallel")
    (opts, tests) = p.parse_args()
    if not tests:
        tests = glob.glob("t[0-9][0-9][0-9][0-9]-*.sh")
    if opts.jobs is None:
        opts.jobs = default_num_jobs()
    print "Running %d tests in parallel" % opts.jobs

    if os.path.exists("trash"):
        os.rename("trash", "trash-being-deleted-%016x" % random.getrandbits(64))
    os.mkdir("trash")
    q = TestQueue(tests, glob.glob("trash-being-deleted-*"))
    w = min(opts.jobs, len(tests))
    for i in range(w):
        start_worker(q)
    for i in range(max(w / 4, 1)):
        start_cleaner(q)
    failed = q.wait()
    if failed:
        print "Failed:"
        for t in sorted(failed):
            print "  ", t
        print "Done"

if __name__ == "__main__":
    main()
