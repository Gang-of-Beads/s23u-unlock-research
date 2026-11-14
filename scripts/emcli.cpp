#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <cstdint>

static void *H;
static void *sym(const char *n) {
    void *p = dlsym(H, n);
    if (!p) printf("missing %s\n", n);
    return p;
}

int main(int argc, char **argv) {
    { void *B0 = dlopen("/system/lib64/libbinder.so", RTLD_NOW|RTLD_GLOBAL);
      auto i0 = B0 ? (int(*)(const char*))dlsym(B0,"_ZN7android12ProcessState14initWithDriverEPKc") : nullptr;
      fprintf(stderr,"pre init=%p\n",(void*)i0);
      if (i0) fprintf(stderr,"pre rc=%d\n", i0("/dev/vndbinder")); }
    fprintf(stderr,"dlopen...\n"); H = dlopen("/vendor/lib64/libengmode_client.so", RTLD_NOW);
    if (!H) { fprintf(stderr,"dlopen: %s\n", dlerror()); return 1; } fprintf(stderr,"ok\n");
    alignas(16) static unsigned char obj[0x12000];
    auto ctor = (void (*)(void *))sym("_ZN7android13engmodeclientC1Ev");
    if (!ctor) return 1;
    fprintf(stderr,"ctor\n"); ctor(obj); fprintf(stderr,"ctor ok\n");
    void **gp = (void **)dlsym(H, "gEngmodeclient");
    if (gp) { *gp = obj; fprintf(stderr,"gEngmodeclient set =%p\n", *gp); } else fprintf(stderr,"no global\n");
    const char *what = argc > 1 ? argv[1] : "status";
    { auto g=(void*(*)(void*))sym("_ZN7android13engmodeclient9getServerEv");
      if (g) { void*r=g(obj); fprintf(stderr,"server=%p\n", r); } }
    fprintf(stderr,"mServer=%p\n", *(void**)obj);
    if (!*(void**)obj) {
      void *B = dlopen("/system/lib64/libbinder.so", RTLD_NOW|RTLD_GLOBAL);
      auto init = B ? (int(*)(const char*))dlsym(B,"_ZN7android12ProcessState14initWithDriverEPKc") : nullptr;
      fprintf(stderr,"vnd init=%p\n",(void*)init);
      if (init) { int rc = init("/dev/vndbinder"); fprintf(stderr,"vnd rc=%d\n", rc); }
      auto g2=(void*(*)(void*))sym("_ZN7android13engmodeclient9getServerEv");
      if (g2) fprintf(stderr,"server2=%p\n", g2(obj));
      fprintf(stderr,"mServer2=%p\n", *(void**)obj);
    }
    if (!strcmp(what,"server")) {
        auto g=(void*(*)(void*))sym("_ZN7android13engmodeclient9getServerEv");
        if (g) { fprintf(stderr,"calling getServer\n"); void*r=g(obj); printf("server=%p\n", r); }
        return 0;
    }
    if (!strcmp(what, "modes")) {
        auto f = (uint64_t (*)(void *))sym("_ZN7android13engmodeclient11getModesbitEv");
        if (f) { fprintf(stderr,"call...\n"); printf("modesbit=0x%llx\n", (unsigned long long)f(obj)); }
    } else if (!strcmp(what, "num")) {
        auto f = (int (*)(void *))sym("_ZN7android13engmodeclient13getNumOfModesEv");
        if (f) printf("numModes=%d\n", f(obj));
    } else if (!strcmp(what, "installed")) {
        auto f = (int (*)(void *))sym("_ZN7android13engmodeclient16isTokenInstalledEv");
        if (f) { fprintf(stderr,"call...\n"); printf("installed=%d\n", f(obj)); }
    } else if (!strcmp(what, "strmodes")) {
        auto f = (char *(*)(void *))sym("_ZN7android13engmodeclient14getStringModesEv");
        if (f) printf("modes=%s\n", f(obj));
    } else if (!strcmp(what, "status")) {
        auto f = (int (*)(void *, int, const uint8_t *, unsigned, const uint8_t *, unsigned, int, int, int))
            sym("_ZN7android13engmodeclient9getStatusEiPKhjS2_jiii");
        if (f) printf("status=%d\n", f(obj, 0, nullptr, 0, nullptr, 0, 0, 0, 0));
    }
    return 0;
}
