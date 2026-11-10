/*
 * gaidheal_runtime.h — runtime for C programs generated from Gàidheal.
 *
 * C99, header-only. The generated program #includes this header and calls
 * gh_* functions over a single operand stack of doubles. Error messages
 * and I/O behaviour match the reference interpreter byte for byte, so
 * interpreted and compiled programs are differentially interchangeable.
 */
#ifndef GAIDHEAL_RUNTIME_H
#define GAIDHEAL_RUNTIME_H

#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef GH_STACK_MAX
#define GH_STACK_MAX 1000
#endif

static double gh_stack[GH_STACK_MAX];
static int gh_sp = 0; /* one past the top element */
static int gh_eof = 0;

static void gh_errorf(const char *fmt, ...) {
    va_list ap;
    fputs("runtime error: ", stderr);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
    exit(1);
}

static void gh_push(double v) {
    if (gh_sp >= GH_STACK_MAX) {
        gh_errorf("stack overflow: the depth limit of %d was reached", GH_STACK_MAX);
    }
    gh_stack[gh_sp++] = v;
}

static double gh_pop(void) {
    if (gh_sp <= 0) {
        gh_errorf("stack underflow: an operation popped more values than the stack had");
    }
    return gh_stack[--gh_sp];
}

static double gh_peek(int index) {
    if (index < 0 || index >= gh_sp) {
        gh_errorf("stack index %d is out of range (depth %d)", index, gh_sp);
    }
    return gh_stack[gh_sp - 1 - index];
}

/* cuir family */
static void gh_copy(int index) { gh_push(gh_peek(index)); }
static void gh_roll(int index) {
    double v = gh_peek(index);
    memmove(&gh_stack[gh_sp - index - 1],
            &gh_stack[gh_sp - index],
            (size_t)index * sizeof(double));
    gh_stack[gh_sp - 1] = v;
}

/* tog family */
static void gh_dup(void) { gh_push(gh_peek(0)); }
static void gh_over(void) { gh_push(gh_peek(1)); }
static void gh_push_depth(void) { gh_push((double)gh_sp); }

/* malairt family */
static void gh_swap(void) {
    double t = gh_peek(0);
    gh_stack[gh_sp - 1] = gh_stack[gh_sp - 2];
    gh_stack[gh_sp - 2] = t;
}
static void gh_reverse(void) {
    for (int i = 0; i < gh_sp / 2; i++) {
        double t = gh_stack[i];
        gh_stack[i] = gh_stack[gh_sp - 1 - i];
        gh_stack[gh_sp - 1 - i] = t;
    }
}
static void gh_tuck(void) {
    double b = gh_pop(); /* top */
    double a = gh_pop(); /* second */
    gh_push(b);
    gh_push(a);
    gh_push(b);
}

/* leig family */
static void gh_drop(void) { (void)gh_pop(); }
static void gh_nip(void) {
    if (gh_sp < 2) {
        gh_errorf("stack underflow: an operation popped more values than the stack had");
    }
    memmove(&gh_stack[gh_sp - 2], &gh_stack[gh_sp - 1], sizeof(double));
    gh_sp--;
}
static void gh_clear(void) { gh_sp = 0; }

/* suim / dealaich families; binary ops pop b then a and push a op b */
static void gh_binary_or_error(double a, double b, double r, int zero_div) {
    if (zero_div) {
        gh_errorf("division by zero");
    }
    gh_push(r);
}

static void gh_add(void) { double b = gh_pop(), a = gh_pop(); gh_push(a + b); }
static void gh_sub(void) { double b = gh_pop(), a = gh_pop(); gh_push(a - b); }
static void gh_mul(void) { double b = gh_pop(), a = gh_pop(); gh_push(a * b); }
static void gh_div(void) {
    double b = gh_pop(), a = gh_pop();
    gh_binary_or_error(a, b, a / b, b == 0.0);
}
static void gh_rem(void) {
    double b = gh_pop(), a = gh_pop();
    gh_binary_or_error(a, b, fmod(a, b), b == 0.0);
}
static void gh_pow(void) { double b = gh_pop(), a = gh_pop(); gh_push(pow(a, b)); }

/* coimeas family */
static void gh_lt(void) { double b = gh_pop(), a = gh_pop(); gh_push(a < b ? 1.0 : 0.0); }
static void gh_gt(void) { double b = gh_pop(), a = gh_pop(); gh_push(a > b ? 1.0 : 0.0); }
static void gh_eq(void) { double b = gh_pop(), a = gh_pop(); gh_push(a == b ? 1.0 : 0.0); }

/*
 * Render a double like the reference interpreter (Rust f64 Display):
 * NaN, infinities, integral values without a fraction, and otherwise the
 * shortest decimal fraction that round-trips.
 */
static void gh_fmt_double(char *buf, size_t bufsz, double v) {
    if (isnan(v)) {
        snprintf(buf, bufsz, "NaN");
        return;
    }
    if (isinf(v)) {
        snprintf(buf, bufsz, v < 0 ? "-inf" : "inf");
        return;
    }
    if (v == floor(v)) {
        snprintf(buf, bufsz, "%.0f", v);
        return;
    }
    for (int prec = 1; prec <= 1100; prec++) {
        snprintf(buf, bufsz, "%.*f", prec, v);
        if (strtod(buf, NULL) == v) {
            return;
        }
    }
    snprintf(buf, bufsz, "%.17f", v);
}

/* abair: print the top as a number plus newline (pops) */
static void gh_print_num(void) {
    char buf[1200];
    gh_fmt_double(buf, sizeof buf, gh_pop());
    puts(buf);
}

/* int-to-u32 conversion with Rust `as u32` saturation semantics */
static uint32_t gh_sat_u32(double d) {
    if (isnan(d) || d <= 0.0) {
        return 0;
    }
    if (d >= 4294967296.0) {
        return 4294967295u;
    }
    return (uint32_t)d;
}

/* n-abair: print the top as a UTF-8 code point, no newline (pops) */
static void gh_print_char(void) {
    double v = gh_pop();
    uint32_t c = gh_sat_u32(round(v));
    if (c > 0x10FFFF || (c >= 0xD800 && c <= 0xDFFF)) {
        char buf[1200];
        gh_fmt_double(buf, sizeof buf, v);
        gh_errorf("`%s` is not a valid Unicode code point", buf);
    }
    if (c < 0x80) {
        putchar((int)c);
    } else if (c < 0x800) {
        putchar((int)(0xC0 | (c >> 6)));
        putchar((int)(0x80 | (c & 0x3F)));
    } else if (c < 0x10000) {
        putchar((int)(0xE0 | (c >> 12)));
        putchar((int)(0x80 | ((c >> 6) & 0x3F)));
        putchar((int)(0x80 | (c & 0x3F)));
    } else {
        putchar((int)(0xF0 | (c >> 18)));
        putchar((int)(0x80 | ((c >> 12) & 0x3F)));
        putchar((int)(0x80 | ((c >> 6) & 0x3F)));
        putchar((int)(0x80 | (c & 0x3F)));
    }
}

/* faigh: read the next whitespace-delimited number (pops nothing) */
static void gh_read_num(void) {
    int c;
    do {
        c = getchar();
    } while (c != EOF && isspace(c));
    if (c == EOF) {
        gh_eof = 1;
        gh_push(-1.0);
        return;
    }
    char token[1024];
    size_t n = 0;
    while (c != EOF && !isspace(c)) {
        if (n + 1 < sizeof token) {
            token[n++] = (char)c;
        }
        c = getchar();
    }
    token[n] = '\0';
    char *end = NULL;
    double v = strtod(token, &end);
    if (end == token || *end != '\0') {
        gh_errorf("could not read a number from input: `%s`", token);
    }
    gh_push(v);
    /* A token that ran to end of stream does NOT set gh_eof here; the
     * next read reports EOF, matching the reference interpreter. */
}

/* fhaigh: read one UTF-8 code point; -1 at EOF (pops nothing) */
static void gh_read_char(void) {
    int first = getchar();
    if (first == EOF) {
        gh_eof = 1;
        gh_push(-1.0);
        return;
    }
    int len;
    if ((unsigned)first < 0x80) {
        len = 1;
    } else if ((first & 0xE0) == 0xC0) {
        len = 2;
    } else if ((first & 0xF0) == 0xE0) {
        len = 3;
    } else if ((first & 0xF8) == 0xF0) {
        len = 4;
    } else {
        gh_errorf("input is not valid UTF-8");
        return;
    }
    uint32_t cp = (uint32_t)(first & (0xFF >> (len == 1 ? 0 : len + 1)));
    for (int i = 1; i < len; i++) {
        int b = getchar();
        if (b == EOF || (b & 0xC0) != 0x80) {
            gh_errorf("input is not valid UTF-8");
        }
        cp = (cp << 6) | (uint32_t)(b & 0x3F);
    }
    gh_push((double)cp);
}

/* bhfaigh: push 1 when the last read hit EOF */
static void gh_eof_flag(void) { gh_push(gh_eof ? 1.0 : 0.0); }

#endif /* GAIDHEAL_RUNTIME_H */
