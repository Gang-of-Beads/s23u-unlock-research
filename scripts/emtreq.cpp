#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <unistd.h>
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    void *H = dlopen("/vendor/lib64/libengmode_server.so", RTLD_NOW);
    if (!H) return 1;
    if (getuid() == 0) { setgid(1000); setuid(1000); }
    alignas(16) static unsigned char obj[0x800];
    ((void (*)(void *))dlsym(H, "_ZN20EngineeringModeWorldC1Ev"))(obj);
    auto init = (int (*)(void *))dlsym(H, "_ZN20EngineeringModeWorld6emInitEv");
    if (init) printf("init=0x%08x\n", (unsigned)init(obj));
    using fn_t = int (*)(void *, const unsigned char *, const unsigned char *, const unsigned char *,
                         const unsigned char *, const unsigned char *, const unsigned char *,
                         unsigned char *, unsigned int *);
    fn_t f = (fn_t)dlsym(H, "_ZN20EngineeringModeWorld17emGetTokenRequestEPKhS1_S1_S1_S1_S1_PhPj");
    printf("f=%p\n", (void*)f);
    if (!f) return 1;
    const char *a[6] = { argc > 1?argv[1]:"", argc > 2?argv[2]:"", argc > 3?argv[3]:"",
                         argc > 4?argv[4]:"", argc > 5?argv[5]:"", argc > 6?argv[6]:"" };
    static unsigned char out[0x2000]; unsigned int n = sizeof out;
    int r = f(obj, (const unsigned char*)a[0], (const unsigned char*)a[1], (const unsigned char*)a[2],
              (const unsigned char*)a[3], (const unsigned char*)a[4], (const unsigned char*)a[5], out, &n);
    printf("rc=0x%08x len=%u\n", (unsigned)r, n);
    if (r == 0) { for (unsigned i = 0; i < n && i < 512; i++) printf("%02x", out[i]); printf("\n"); }
    return 0;
}
