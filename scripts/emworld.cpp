#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <unistd.h>
#include <android/log.h>

int main(int argc, char **argv) {
    if (getuid() == 0) { setgid(1000); setuid(1000); }
    fprintf(stderr, "uid=%d euid=%d\n", getuid(), geteuid());
    void *H = dlopen("/vendor/lib64/libengmode_server.so", RTLD_NOW);
    if (!H) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
    alignas(16) static unsigned char obj[0x800];
    auto ctor = (void (*)(void *))dlsym(H, "_ZN20EngineeringModeWorldC1Ev");
    if (!ctor) { fprintf(stderr, "no ctor\n"); return 1; }
    ctor(obj);
    auto init = (int (*)(void *))dlsym(H, "_ZN20EngineeringModeWorld6emInitEv");
    if (init && !(argc > 1 && argv[1][0] == 'n')) fprintf(stderr, "emInit=%d\n", init(obj));
    auto inst = (int (*)(void *, unsigned char *))dlsym(H, "_ZN20EngineeringModeWorld18emIsTokenInstalledEPh");
    if (inst) { unsigned char v = 0xff; int r = inst(obj, &v); printf("installed rc=%d val=%u\n", r, v); }
    auto mb = (int (*)(void *, unsigned char *, unsigned int *))dlsym(H, "_ZN20EngineeringModeWorld13emGetModesBitEPhPj");
    if (mb) {
        unsigned char buf[64]; memset(buf, 0, sizeof buf); unsigned int len = sizeof buf;
        int r = mb(obj, buf, &len);
        printf("modesbit rc=%d len=%u:", r, len);
        for (unsigned i = 0; i < len && i < 32; i++) printf(" %02x", buf[i]);
        printf("\n");
    }
    return 0;
}
