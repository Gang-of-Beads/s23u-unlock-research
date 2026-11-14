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
    alignas(16) static unsigned char obj[0x1000];
    ((void (*)(void *))dlsym(H, "_ZN20EngineeringModeWorldC1Ev"))(obj);
    auto init = (int (*)(void *))dlsym(H, "_ZN20EngineeringModeWorld6emInitEv");
    if (init) printf("init=0x%08x\n", (unsigned)init(obj));
    auto prep = (void (*)(void *, int, int))dlsym(H, "_ZN20EngineeringModeWorld14preparePayloadEii");
    if (!prep) { printf("no prep\n"); return 1; }
    int cmd = argc > 1 ? atoi(argv[1]) : 21;
    int sub = argc > 2 ? atoi(argv[2]) : 1;
    prep(obj, cmd, sub);
    unsigned char *p = *(unsigned char **)(obj + 0x70);
    printf("payload=%p cmd=%d sub=%d\n", (void*)p, cmd, sub);
    if (!p) return 1;
    // 打印前 64 字节，便于比对布局
    printf("hdr:");
    for (int i = 0; i < 64; i++) printf(" %02x", p[i]);
    printf("\n");
    auto proc = (int (*)(void *, unsigned char *, unsigned, unsigned char *, unsigned *))
        dlsym(H, "_ZN20EngineeringModeWorld9emProcessEP16em_req_payload_tjP16em_rsp_payload_tPj");
    if (!proc) { printf("no proc\n"); return 1; }
    static unsigned char rsp[0x400];
    unsigned rlen = sizeof rsp;
    int r = proc(obj, p, 0x40, rsp, &rlen);
    printf("rc=0x%08x rlen=%u\n", (unsigned)r, rlen);
    printf("rsp:");
    for (unsigned i = 0; i < rlen && i < 64; i++) printf(" %02x", rsp[i]);
    printf("\n");
    return 0;
}
