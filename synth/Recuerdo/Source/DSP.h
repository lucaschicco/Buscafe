// Recuerdo — bloques DSP básicos (sin dependencias de JUCE).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace rcd
{
constexpr float pi    = 3.14159265358979f;
constexpr float twoPi = 6.28318530717959f;

//==============================================================================
// Ruido / aleatoriedad barata y determinista (apta para el hilo de audio).
struct Rng
{
    uint32_t state = 0x12345678u;
    explicit Rng (uint32_t seed = 0x12345678u) : state (seed ? seed : 1u) {}

    uint32_t nextU32() noexcept
    {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        return state;
    }
    float uni() noexcept { return (float) (nextU32() >> 8) * (1.0f / 16777216.0f); } // [0,1)
    float bi() noexcept  { return uni() * 2.0f - 1.0f; }                             // [-1,1)
};

// tanh racional: suave, barata y acotada.
inline float softClip (float x) noexcept
{
    x = std::clamp (x, -3.0f, 3.0f);
    const float x2 = x * x;
    return x * (27.0f + x2) / (27.0f + 9.0f * x2);
}

inline float onePoleCoef (float hz, float sr) noexcept
{
    return 1.0f - std::exp (-twoPi * hz / sr);
}

//==============================================================================
// Oscilador saw/square con PolyBLEP (antialiasing de las discontinuidades).
inline float polyBlep (float t, float dt) noexcept
{
    if (t < dt)
    {
        t /= dt;
        return t + t - t * t - 1.0f;
    }
    if (t > 1.0f - dt)
    {
        t = (t - 1.0f) / dt;
        return t * t + t + t + 1.0f;
    }
    return 0.0f;
}

struct BlepOsc
{
    float phase = 0.0f, inc = 0.0f;

    void setFreq (float hz, float sr) noexcept { inc = std::clamp (hz / sr, 0.0f, 0.45f); }

    // Devuelve saw y square de la misma fase (comparten el acumulador).
    inline void next (float& saw, float& sq) noexcept
    {
        const float t = phase;
        saw = 2.0f * t - 1.0f - polyBlep (t, inc);

        float s = t < 0.5f ? 1.0f : -1.0f;
        s += polyBlep (t, inc);
        float t2 = t + 0.5f;
        if (t2 >= 1.0f) t2 -= 1.0f;
        s -= polyBlep (t2, inc);
        sq = s;

        phase += inc;
        if (phase >= 1.0f) phase -= 1.0f;
    }

    inline float nextSquare() noexcept
    {
        float a, b;
        next (a, b);
        return b;
    }
};

//==============================================================================
// Filtro ladder 4 polos (TPT / zero-delay feedback) con saturación en la entrada
// de la realimentación, estilo transistor ladder.
struct Ladder
{
    float s[4] {};

    void reset() noexcept { s[0] = s[1] = s[2] = s[3] = 0.0f; }

    // g = tan(pi * fc / fs), k = resonancia (0..4, autooscila cerca de 4)
    inline float process (float x, float g, float k) noexcept
    {
        const float G   = g / (1.0f + g);
        const float inv = 1.0f / (1.0f + g);
        const float G2 = G * G, G3 = G2 * G, G4 = G3 * G;

        const float sigma = G3 * s[0] * inv + G2 * s[1] * inv + G * s[2] * inv + s[3] * inv;
        const float y4    = (G4 * x + sigma) / (1.0f + k * G4);

        float u = softClip (x - k * y4);

        for (int i = 0; i < 4; ++i)
        {
            const float v = (u - s[i]) * G;
            const float y = v + s[i];
            s[i] = y + v;
            u = y;
        }
        // compensación de graves perdidos por la resonancia
        return u * (1.0f + 0.5f * k);
    }
};

//==============================================================================
// Línea de retardo con lectura fraccional (Hermite, 4 puntos).
struct DelayLine
{
    std::vector<float> buf;
    int w = 0, mask = 0;

    void init (int minSize)
    {
        int size = 1;
        while (size < minSize) size <<= 1;
        buf.assign ((size_t) size, 0.0f);
        mask = size - 1;
        w = 0;
    }
    void clear() { std::fill (buf.begin(), buf.end(), 0.0f); }

    inline void push (float x) noexcept
    {
        buf[(size_t) w] = x;
        w = (w + 1) & mask;
    }

    // delay en muestras (>= 2). 0 = muestra más reciente.
    inline float read (float delay) const noexcept
    {
        const float r = (float) (w - 1) - delay;
        const float fl = std::floor (r);
        const float f = r - fl;
        const int i = (int) fl;
        const float y0 = buf[(size_t) ((i - 1) & mask)];
        const float y1 = buf[(size_t) (i & mask)];
        const float y2 = buf[(size_t) ((i + 1) & mask)];
        const float y3 = buf[(size_t) ((i + 2) & mask)];
        const float c1 = 0.5f * (y2 - y0);
        const float c2 = y0 - 2.5f * y1 + 2.0f * y2 - 0.5f * y3;
        const float c3 = 0.5f * (y3 - y0) + 1.5f * (y1 - y2);
        return ((c3 * f + c2) * f + c1) * f + y1;
    }
};

//==============================================================================
// Chorus estéreo estilo Juno: una línea BBD, dos lecturas con LFO triangular
// en contrafase (L = +LFO, R = -LFO). Un solo control "amount".
struct JunoChorus
{
    DelayLine line;
    float sr = 48000.0f, phase = 0.0f, lpL = 0.0f, lpR = 0.0f, lpCoef = 0.5f;

    void prepare (float sampleRate)
    {
        sr = sampleRate;
        line.init ((int) (sr * 0.02f) + 8);
        lpCoef = onePoleCoef (7500.0f, sr); // oscurecimiento tipo BBD
        reset();
    }
    void reset() { line.clear(); phase = 0.0f; lpL = lpR = 0.0f; }

    inline void process (float in, float amount, float& outL, float& outR) noexcept
    {
        line.push (in);

        const float rate  = 0.45f + 0.45f * amount;      // Hz (Juno I ~0.5, II ~0.8)
        const float depth = 0.0005f + 0.0015f * amount;  // s
        const float base  = 0.0035f;                     // s

        phase += rate / sr;
        if (phase >= 1.0f) phase -= 1.0f;
        float tri = 4.0f * std::abs (phase - 0.5f) - 1.0f; // -1..1
        tri = tri * (1.5f - 0.5f * tri * tri);             // redondea los picos

        const float dL = (base + depth * tri) * sr;
        const float dR = (base - depth * tri) * sr;
        lpL += (line.read (dL) - lpL) * lpCoef;
        lpR += (line.read (dR) - lpR) * lpCoef;

        const float wet = 0.75f * amount;
        const float dry = 1.0f - 0.25f * amount;
        outL = in * dry + lpL * wet;
        outR = in * dry + lpR * wet;
    }
};

//==============================================================================
// "Cinta vieja": wow + flutter (modulación de pitch vía retardo), deriva
// aleatoria, pérdida de agudos, hiss suave que sigue a la señal y, con Age
// alto, cortes ("dropouts") de nivel.
struct TapeStage
{
    DelayLine line[2];
    float sr = 48000.0f;
    float wowPhase = 0.0f, flutterPhase = 0.0f;
    float drift = 0.0f, driftTarget = 0.0f; int driftCount = 0;
    float lp1[2] {}, lp2[2] {};
    float hissLp[2] {}, hissHp[2] {};
    float envFollow = 0.0f;
    float dropGain = 1.0f, dropTarget = 1.0f; int dropCount = 0;
    Rng rng { 0xBADC0FFEu };

    void prepare (float sampleRate)
    {
        sr = sampleRate;
        for (auto& l : line) l.init ((int) (sr * 0.03f) + 8);
        reset();
    }
    void reset()
    {
        for (auto& l : line) l.clear();
        wowPhase = flutterPhase = drift = driftTarget = 0.0f;
        driftCount = 0;
        for (int c = 0; c < 2; ++c) lp1[c] = lp2[c] = hissLp[c] = hissHp[c] = 0.0f;
        envFollow = 0.0f;
        dropGain = dropTarget = 1.0f;
        dropCount = 0;
    }

    inline void process (float& L, float& R, float age) noexcept
    {
        const float a2 = age * age, a3 = a2 * age;

        // --- Modulación de pitch -------------------------------------------
        wowPhase += 0.55f / sr;
        if (wowPhase >= 1.0f) wowPhase -= 1.0f;
        flutterPhase += 6.3f / sr;
        if (flutterPhase >= 1.0f) flutterPhase -= 1.0f;

        if (--driftCount <= 0)
        {
            driftTarget = rng.bi();
            driftCount = (int) (sr * (0.4f + 0.8f * rng.uni()));
        }
        drift += (driftTarget - drift) * (1.5f / sr);

        const float wowDepth     = 0.00025f * age + 0.0020f * a3; // s
        const float flutterDepth = 0.00004f * age + 0.00004f * a2;
        const float driftDepth   = 0.0025f * a2;
        const float base = 0.0003f + (wowDepth + flutterDepth + driftDepth) * 1.05f;

        const float mod = base
                        + wowDepth * std::sin (twoPi * wowPhase)
                        + flutterDepth * std::sin (twoPi * flutterPhase)
                        + driftDepth * drift;
        const float d = std::max (2.0f, mod * sr);

        line[0].push (L);
        line[1].push (R);
        float x[2] = { line[0].read (d), line[1].read (d) };

        // --- Pérdida de agudos (2 polos, 18 kHz -> ~4.5 kHz) ---------------
        const float fc = 18000.0f * std::pow (0.25f, age);
        const float c = onePoleCoef (std::min (fc, 0.45f * sr), sr);

        // --- Hiss que sigue a la señal (no suena con el sinte en silencio) --
        const float lvl = std::max (std::abs (L), std::abs (R));
        envFollow += (lvl - envFollow) * (lvl > envFollow ? 0.002f : 0.00003f);
        const float gate = std::min (1.0f, envFollow * 12.0f);
        const float hissAmt = 0.008f * std::pow (age, 1.5f) * gate;

        // --- Dropouts (Age > 0.6) -------------------------------------------
        if (age > 0.6f)
        {
            if (--dropCount <= 0)
            {
                const bool dip = dropTarget >= 0.99f && rng.uni() < (age - 0.6f) * 1.2f;
                dropTarget = dip ? 0.35f + 0.4f * rng.uni() : 1.0f;
                dropCount = (int) (sr * (dip ? 0.04f + 0.1f * rng.uni() : 0.25f + 0.5f * rng.uni()));
            }
        }
        else
            dropTarget = 1.0f;
        dropGain += (dropTarget - dropGain) * 0.003f;

        for (int ch = 0; ch < 2; ++ch)
        {
            lp1[ch] += (x[ch] - lp1[ch]) * c;
            lp2[ch] += (lp1[ch] - lp2[ch]) * c;

            const float n = rng.bi();
            hissLp[ch] += (n - hissLp[ch]) * 0.35f;   // suaviza el ruido blanco
            hissHp[ch] += (hissLp[ch] - hissHp[ch]) * 0.02f;
            const float hiss = (hissLp[ch] - hissHp[ch]) * hissAmt;

            x[ch] = lp2[ch] * dropGain + hiss;
        }

        // leve saturación de cinta
        const float drive = 1.0f + 0.8f * age;
        L = softClip (x[0] * drive) / drive;
        R = softClip (x[1] * drive) / drive;
    }
};

//==============================================================================
// Saturación analógica suave (asimétrica -> armónicos pares). Pensada para
// correr sobremuestreada.
inline float warmthShape (float x, float w) noexcept
{
    const float drive = 1.0f + 7.0f * w * w + 1.5f * w;
    const float bias  = 0.2f * w;
    const float y = softClip (x * drive + bias) - softClip (bias);
    // compensación de nivel aproximada
    return y / (1.0f + 0.55f * (drive - 1.0f));
}

struct DcBlocker
{
    float x1 = 0.0f, y1 = 0.0f, r = 0.9995f;
    void prepare (float sr) { r = 1.0f - twoPi * 10.0f / sr; x1 = y1 = 0.0f; }
    inline float process (float x) noexcept
    {
        const float y = x - x1 + r * y1;
        x1 = x;
        y1 = y;
        return y;
    }
};

} // namespace rcd
