#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <unistd.h>
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    void *H = dlopen("/vendor/lib64/libengmode_server.so", RTLD_NOW);
    if (!H) { printf("dlopen fail\n"); return 1; }
    if (getuid() == 0) { setgid(1000); setuid(1000); }
    alignas(16) static unsigned char obj[0x800];
    ((void (*)(void *))dlsym(H, "_ZN20EngineeringModeWorldC1Ev"))(obj);
    auto init = (int (*)(void *))dlsym(H, "_ZN20EngineeringModeWorld6emInitEv");
    if (!init) printf("noinit: %s\n", dlerror()); else printf("init=0x%08x\n", (unsigned)init(obj));
    auto proc = (int (*)(void *, unsigned char *, unsigned, unsigned char *, unsigned *))
        dlsym(H, "_ZN20EngineeringModeWorld9emProcessEP16em_req_payload_tjP16em_rsp_payload_tPj");
    printf("proc=%p\n", (void*)proc);
    if (!proc) return 1;
    static unsigned char req[0x200], rsp[0x200];
    unsigned cmd = argc > 1 ? (unsigned)strtoul(argv[1], 0, 0) : 20;
    unsigned off = argc > 2 ? (unsigned)strtoul(argv[2], 0, 0) : 0x10;
    memset(req, 0, sizeof req); memset(rsp, 0, sizeof rsp);
    *(unsigned *)(req + 8) = cmd;
    // data: argv[3..] each u16 placed at off
    int n = 0;
    for (int i = 3; i < argc; i++) { *(unsigned short *)(req + off + 2 * n) = (unsigned short)strtoul(argv[i], 0, 0); n++; }
    unsigned len = off + 2 * n + 0x40;
    unsigned rlen = sizeof rsp;
    int r = proc(obj, req, len, rsp, &rlen);
    printf("cmd=%u rc=0x%08x rlen=%u\n", cmd, (unsigned)r, rlen);
    return 0;
}
