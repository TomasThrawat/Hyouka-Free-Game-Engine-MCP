#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

typedef struct _XDisplay Display;
typedef const char *(*glx_query_extensions_string_fn)(Display *, int);
typedef void *(*glx_get_proc_address_fn)(const unsigned char *);

const char *glXQueryExtensionsString(Display *display, int screen) {
    static glx_query_extensions_string_fn real_fn;
    static char merged[16384];

    if (!real_fn) {
        real_fn = (glx_query_extensions_string_fn)dlsym(RTLD_NEXT, "glXQueryExtensionsString");
    }

    const char *base = real_fn ? real_fn(display, screen) : "";
    if (strstr(base, "GLX_MESA_swap_control") != NULL) {
        return base;
    }

    int written = snprintf(merged, sizeof(merged), "%s GLX_MESA_swap_control", base);
    if (written < 0) {
        return base;
    }
    merged[sizeof(merged) - 1] = '\0';
    return merged;
}

int glXSwapIntervalMESA(unsigned int interval) {
    (void)interval;
    return 0;
}

void *glXGetProcAddressARB(const unsigned char *name) {
    if (name && strcmp((const char *)name, "glXSwapIntervalMESA") == 0) {
        return (void *)&glXSwapIntervalMESA;
    }

    static glx_get_proc_address_fn real_fn;
    if (!real_fn) {
        real_fn = (glx_get_proc_address_fn)dlsym(RTLD_NEXT, "glXGetProcAddressARB");
    }

    return real_fn ? real_fn(name) : NULL;
}

void *glXGetProcAddress(const unsigned char *name) {
    return glXGetProcAddressARB(name);
}
