#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <unistd.h>
int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    void *H = dlopen("/vendor/lib64/libengmode_server.so", RTLD_NOW);
    if (!H) { printf("dlopen fail\n"); return 1; }
    if (getuid() == 0) { setgid(1000); setuid(1000); }
    alignas(16) static unsigned char obj[0x800];
    auto ctor = (void (*)(void *))dlsym(H, "_ZN20EngineeringModeWorldC1Ev");
    ctor(obj);
    auto init = (int (*)(void *))dlsym(H, "_ZN20EngineeringModeWorld6emInitEv");
    printf("init=0x%08x\n", (unsigned)init(obj));
    auto tr = (int (*)(void *, unsigned char *, unsigned int *))dlsym(H, "_ZN20EngineeringModeWorld16emGetTimeRequestEPhPj");
    printf("tr=%p\n", (void*)tr);
    unsigned char buf[64]; memset(buf, 0, sizeof buf); unsigned int len = sizeof buf;
    int r = tr(obj, buf, &len);
    printf("timeReq rc=0x%08x len=%u:", (unsigned)r, len);
    for (unsigned i = 0; i < len && i < 24; i++) printf(" %02x", buf[i]);
    printf("\n");
    return 0;
}
