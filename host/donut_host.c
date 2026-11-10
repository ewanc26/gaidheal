/*
 * donut_host — a bespoke SDL2 engine for esolang demo programs.
 *
 * The language program (examples/donut_engine.gaidheal) computes a
 * spinning, orbit-lit torus and streams a per-frame vertex protocol
 * on stdout (one value per line, gaidheal's `abair`):
 *
 *   F                                  begin frame
 *   px                                 vertex 0 screen x
 *   py                                 vertex 0 screen y
 *   z                                  vertex 0 camera-space depth (z + 5)
 *   intensity                          vertex 0 lighting intensity
 *   ... 1499 more vertices, in i*V_STEPS+j order (i in 0..49, j in 0..29)
 *   S                                  swap/present
 *
 * The host is a faithful embed of the canonical renderer in
 * doughnut.c (torus mesh R_MAJOR=2.0 / R_MINOR=0.8, U_STEPS=50 /
 * V_STEPS=30, fov=500, 800x600 z-buffered Gouraud triangle
 * rasterization, purple-pink palette; the cyan wireframe rule is
 * ported verbatim but this engine runs with the flag off).  The
 * language side is responsible for angles, the orbiting light,
 * attenuation and projection, matching doughnut.c frame-for-frame.
 *
 * The stream is finite (the example runs FRAMES frames and stops).
 * After the producer's stream ends, the host replays the recorded
 * frames forever. Headless: --frames N exits after N presented frames
 * (SDL_VIDEODRIVER=dummy works); --size W H resizes the window but the
 * raster is always the canonical 800x600.
 *
 * Build: cc -std=c99 $(sdl2-config --cflags --libs) -o host_bin host/donut_host.c
 */
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIDTH 800
#define HEIGHT 600

#define R_MAJOR 2.0f
#define R_MINOR 0.8f
#define U_STEPS 50
#define V_STEPS 30
#define N_VERTS (U_STEPS * V_STEPS)
#define MAX_FRAMES 8192

typedef struct {
    float x, y, z;
} Vector3;

typedef struct {
    int i0, i1, i2;
} Triangle;

static Triangle triangles[N_VERTS * 2];
static int total_triangles = 0;

static float zbuffer[WIDTH * HEIGHT];
static Uint32 framebuffer[WIDTH * HEIGHT];

/* One recorded frame: the producer's per-vertex stream. */
typedef struct {
    float px[N_VERTS], py[N_VERTS], z[N_VERTS], intensity[N_VERTS];
    int count;
} VertexFrame;

static VertexFrame *frames = NULL;
static int nframes = 0, frame_cap = 0;
static int recording = 1;

static void generate_torus(void) {
    for (int i = 0; i < U_STEPS; i++) {
        int next_i = (i + 1) % U_STEPS;
        for (int j = 0; j < V_STEPS; j++) {
            int next_j = (j + 1) % V_STEPS;

            int current = i * V_STEPS + j;
            int right = next_i * V_STEPS + j;
            int down = i * V_STEPS + next_j;
            int diag = next_i * V_STEPS + next_j;

            triangles[total_triangles++] = (Triangle){current, right, diag};
            triangles[total_triangles++] = (Triangle){current, diag, down};
        }
    }
}

/* doughnut.c's draw_triangle, wireframe flag passed in (this engine uses 0). */
static void draw_triangle(Vector3 v0, Vector3 v1, Vector3 v2,
                          float int0, float int1, float int2,
                          int wireframe_on) {
    int min_x = (int)fmaxf(0, fminf(v0.x, fminf(v1.x, v2.x)));
    int max_x = (int)fminf(WIDTH - 1, fmaxf(v0.x, fmaxf(v1.x, v2.x)));
    int min_y = (int)fmaxf(0, fminf(v0.y, fminf(v1.y, v2.y)));
    int max_y = (int)fminf(HEIGHT - 1, fmaxf(v0.y, fmaxf(v1.y, v2.y)));

    float area = (v1.y - v2.y) * (v0.x - v2.x) + (v2.x - v1.x) * (v0.y - v2.y);
    if (fabsf(area) < 1e-5f) return;

    for (int y = min_y; y <= max_y; y++) {
        for (int x = min_x; x <= max_x; x++) {
            float px = (float)x + 0.5f;
            float py = (float)y + 0.5f;

            float w0 = ((v1.y - v2.y) * (px - v2.x) + (v2.x - v1.x) * (py - v2.y)) / area;
            float w1 = ((v2.y - v0.y) * (px - v2.x) + (v0.x - v2.x) * (py - v2.y)) / area;
            float w2 = 1.0f - w0 - w1;

            if (w0 >= 0.0f && w1 >= 0.0f && w2 >= 0.0f) {
                float inv_z = w0 * (1.0f / v0.z) + w1 * (1.0f / v1.z) + w2 * (1.0f / v2.z);
                float z = 1.0f / inv_z;

                int idx = y * WIDTH + x;
                if (z < zbuffer[idx]) {
                    zbuffer[idx] = z;

                    float intensity = (w0 * (int0 / v0.z) + w1 * (int1 / v1.z) + w2 * (int2 / v2.z)) / inv_z;

                    if (wireframe_on && (w0 < 0.04f || w1 < 0.04f || w2 < 0.04f)) {
                        framebuffer[idx] = 0xFF00FFFF;
                    } else {
                        Uint32 r = (Uint32)(fminf(1.0f, intensity * 0.9f) * 255);
                        Uint32 g = (Uint32)(fminf(1.0f, intensity * 0.4f) * 255);
                        Uint32 b = (Uint32)(fminf(1.0f, intensity * 0.9f) * 255);
                        framebuffer[idx] = (0xFF << 24) | (r << 16) | (g << 8) | b;
                    }
                }
            }
        }
    }
}

static void render_frame(const VertexFrame *f) {
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        zbuffer[i] = 1e9f;
        framebuffer[i] = 0xFF101010;
    }

    Vector3 verts[N_VERTS];
    for (int i = 0; i < f->count; i++) {
        verts[i].x = f->px[i];
        verts[i].y = f->py[i];
        verts[i].z = f->z[i];
    }

    for (int t = 0; t < total_triangles; t++) {
        Triangle tri = triangles[t];
        if (tri.i0 >= f->count || tri.i1 >= f->count || tri.i2 >= f->count) continue;
        draw_triangle(verts[tri.i0], verts[tri.i1], verts[tri.i2],
                      f->intensity[tri.i0], f->intensity[tri.i1], f->intensity[tri.i2],
                      0);
    }
}

static void record_frame(const VertexFrame *f) {
    if (!recording) return;
    if (nframes == frame_cap) {
        int next = frame_cap ? frame_cap * 2 : 64;
        if (next > MAX_FRAMES) next = MAX_FRAMES;
        if (nframes >= MAX_FRAMES) { recording = 0; return; }
        frames = realloc(frames, (size_t)next * sizeof(VertexFrame));
        if (!frames) { recording = 0; return; }
        frame_cap = next;
    }
    if (nframes >= MAX_FRAMES) { recording = 0; return; }
    frames[nframes++] = *f;
}

int main(int argc, char **argv) {
    int present_limit = -1;
    int width = WIDTH, height = HEIGHT;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) present_limit = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--size") && i + 2 < argc) { width = atoi(argv[++i]); height = atoi(argv[++i]); }
    }

    generate_torus();

    /* Vertex-stream protocol: F / 4 x 1500 numbers / S. */
    if (SDL_Init(SDL_INIT_VIDEO) != 0) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Window *win = SDL_CreateWindow("gaidheal donut - orbiting light", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                       width, height, SDL_WINDOW_SHOWN);
    if (!win) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ren) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    if (!ren) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Texture *tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, WIDTH, HEIGHT);
    if (!tex) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }

    int presented = 0;
    int running = 1;
    int in_frame = 0;
    VertexFrame cur;
    float pending[4];
    int npending = 0;
    char tok[64];
    long bad = 0;

    while (running && scanf("%63s", tok) == 1) {
        if (!strcmp(tok, "F")) {
            cur.count = 0;
            npending = 0;
            in_frame = 1;
        } else if (!strcmp(tok, "S")) {
            if (!in_frame) { bad++; continue; }
            render_frame(&cur);
            record_frame(&cur);
            SDL_UpdateTexture(tex, NULL, framebuffer, WIDTH * sizeof(Uint32));
            SDL_RenderClear(ren);
            SDL_RenderCopy(ren, tex, NULL, NULL);
            SDL_RenderPresent(ren);
            presented++;
            in_frame = 0;
            if (present_limit >= 0 && presented >= present_limit) running = 0;
        } else {
            char *end = NULL;
            double v = strtod(tok, &end);
            if (end == tok || *end != '\0') { bad++; continue; }
            if (!in_frame || cur.count >= N_VERTS) { bad++; continue; }
            pending[npending++] = (float)v;
            if (npending == 4) {
                cur.px[cur.count] = pending[0];
                cur.py[cur.count] = pending[1];
                cur.z[cur.count] = pending[2];
                cur.intensity[cur.count] = pending[3];
                cur.count++;
                npending = 0;
            }
        }
    }
    if (bad) fprintf(stderr, "donut_host: %ld malformed tokens skipped\n", bad);
    if (nframes == 0) { fprintf(stderr, "donut_host: no frames in input\n"); return 2; }
    fprintf(stderr, "donut_host: %d frames recorded, %d presented live\n", nframes, presented);

    /* Replay recorded frames forever (finite demos). */
    while (running) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = 0;
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) running = 0;
        }
        VertexFrame *f = &frames[presented % nframes];
        render_frame(f);
        SDL_UpdateTexture(tex, NULL, framebuffer, WIDTH * sizeof(Uint32));
        SDL_RenderClear(ren);
        SDL_RenderCopy(ren, tex, NULL, NULL);
        SDL_RenderPresent(ren);
        presented++;
        if (present_limit >= 0 && presented >= present_limit) running = 0;
        if (present_limit < 0) SDL_Delay(16);
    }

    SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
