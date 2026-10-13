/* Linux x86_64 native-job launcher: no new privileges, no sockets, bounded resources. */
#include <errno.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
    struct rlimit cpu = {60, 60};
    struct rlimit memory = {4ULL * 1024 * 1024 * 1024, 4ULL * 1024 * 1024 * 1024};
    struct rlimit output = {64ULL * 1024 * 1024, 64ULL * 1024 * 1024};
    struct rlimit files = {64, 64};
    struct rlimit core = {0, 0};
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socketpair, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {sizeof(filter) / sizeof(filter[0]), filter};
    if (argc < 2) { fprintf(stderr, "usage: netdeny /absolute/executable [args...]\n"); return 2; }
    if (setrlimit(RLIMIT_CPU, &cpu) || setrlimit(RLIMIT_AS, &memory) ||
        setrlimit(RLIMIT_FSIZE, &output) || setrlimit(RLIMIT_NOFILE, &files) ||
        setrlimit(RLIMIT_CORE, &core) || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) {
        perror("native sandbox initialization"); return 2;
    }
    /* The Python caller closes inherited descriptors and supplies a minimal environment. */
    execv(argv[1], argv + 1);
    perror("native executable");
    return 2;
}
