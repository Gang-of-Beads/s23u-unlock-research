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
    auto inst = (int (*)(void *, unsigned char *, unsigned int))dlsym(H, "_ZN20EngineeringModeWorld14emTokenInstallEPhj");
    printf("inst=%p\n", (void*)inst);
    FILE *f = fopen(argv[1], "rb");
    if (!f) { printf("no file\n"); return 1; }
    static unsigned char buf[0x4000];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    printf("len=%zu\n", n);
    int r = inst(obj, buf, (unsigned)n);
    printf("install rc=0x%08x\n", (unsigned)r);
    return 0;
}
