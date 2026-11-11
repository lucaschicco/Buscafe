// Recuerdo — motor de voces: 8 voces poly o 1 voz mono con legato/glide.
#pragma once

#include "DSP.h"
#include <array>

namespace rcd
{
// Valores que cambian muestra a muestra (ya suavizados).
struct Frame
{
    float tone = 0.5f;    // 0..1
    float depth = 0.0f;   // 0..1
    float detune = 0.0f;  // 0..1
    float shape = 0.0f;   // 0 saw .. 1 square
    float vibrato = 0.0f; // 0..1
};

// Coeficientes que se calculan una vez por bloque.
struct BlockCoefs
{
    float attackCoef = 1.0f;
    float releaseCoef = 0.0f;
    float glideCoef = 1.0f;  // 1 = sin glide
    float fenvAmount = 0.0f; // semitonos de apertura del filtro por velocity
};

struct Voice
{
    int note = -1;
    bool active = false, gate = false, sustained = false, attacking = false;
    float pitch = 60.0f, target = 60.0f, vel = 1.0f;
    float env = 0.0f, fenv = 0.0f, vibRamp = 0.0f;
    float drift = 0.0f, driftTarget = 0.0f;
    int driftCount = 0;
    uint32_t stamp = 0;
    BlepOsc o1, o2, sub;
    Ladder filt;
    Rng rng;
};

class SynthEngine
{
public:
    static constexpr int maxVoices = 8;

    void prepare (double sampleRate)
    {
        sr = (float) sampleRate;
        fenvDecay = std::exp (-1.0f / (0.30f * sr));
        driftSmooth = 1.0f / (0.6f * sr);
        vibRampCoef = 1.0f / (0.35f * sr);
        uint32_t seed = 0xC0FFEE11u;
        for (auto& v : voices) v.rng = Rng (seed += 0x9E3779B9u);
        reset();
    }

    void reset()
    {
        for (auto& v : voices)
        {
            v.active = v.gate = v.sustained = v.attacking = false;
            v.env = 0.0f;
            v.note = -1;
            v.filt.reset();
        }
        heldCount = 0;
        sustainPedal = false;
    }

    void setBlockParams (float attackSec, float releaseSec, float glideSec, bool monoMode)
    {
        if (monoMode != mono)
        {
            // al cambiar de modo, soltamos todo con release (sin clicks)
            for (auto& v : voices) { v.gate = false; v.sustained = false; }
            heldCount = 0;
            mono = monoMode;
        }
        // ataque exponencial hacia 1.25 (curva tipo analógica): llega a 1 en ~attackSec
        coefs.attackCoef = 1.0f - std::exp (-1.79f / (std::max (attackSec, 0.0005f) * sr));
        coefs.releaseCoef = std::exp (-6.9f / (std::max (releaseSec, 0.003f) * sr));
        coefs.glideCoef = glideSec < 0.001f ? 1.0f : 1.0f - std::exp (-1.0f / (glideSec * 0.4f * sr));
        // el "pluck" del filtro sólo se nota con ataques cortos
        coefs.fenvAmount = 20.0f * std::clamp (1.0f - attackSec / 0.4f, 0.0f, 1.0f);
    }

    void setPitchBend (float semis) { bend = semis; }
    void setModWheel (float v) { modWheel = v; }

    void setSustain (bool down)
    {
        sustainPedal = down;
        if (! down)
            for (auto& v : voices) v.sustained = false;
    }

    void allNotesOff()
    {
        for (auto& v : voices) { v.gate = false; v.sustained = false; }
        heldCount = 0;
    }

    void noteOn (int note, float velocity)
    {
        if (mono) monoNoteOn (note, velocity);
        else      polyNoteOn (note, velocity);
        lastPitch = (float) note;
    }

    void noteOff (int note)
    {
        if (mono) { monoNoteOff (note); return; }

        for (auto& v : voices)
            if (v.active && v.gate && v.note == note)
            {
                v.gate = false;
                v.sustained = sustainPedal;
            }
    }

    inline float renderSample (const Frame& f) noexcept
    {
        // LFO de vibrato global (seno 5.3 Hz)
        lfoPhase += 5.3f / sr;
        if (lfoPhase >= 1.0f) lfoPhase -= 1.0f;
        const float lfo = std::sin (twoPi * lfoPhase);
        const float vibCents = 45.0f * f.vibrato * std::sqrt (f.vibrato) + 35.0f * modWheel;

        // detune: 0..40 cents entre los dos osciladores
        const float cents = 40.0f * f.detune * f.detune;
        const float detUp = std::exp2 (cents * 0.5f / 1200.0f);
        const float detDown = 1.0f / detUp;
        const float osc2Gain = std::clamp (f.detune * 5.0f, 0.0f, 1.0f);
        const float oscNorm = 1.0f / (1.0f + 0.6f * osc2Gain);

        const float baseCutoff = 60.0f * std::exp2 (f.tone * 8.4f); // 60 Hz .. 20 kHz
        const float k = 1.35f;
        const float maxFc = 0.45f * sr;

        float out = 0.0f;
        for (auto& v : voices)
        {
            if (! v.active) continue;

            // glide
            if (coefs.glideCoef >= 1.0f) v.pitch = v.target;
            else v.pitch += (v.target - v.pitch) * coefs.glideCoef;

            // deriva analógica lenta por voz (±3 cents)
            if (--v.driftCount <= 0)
            {
                v.driftTarget = v.rng.bi() * 3.0f;
                v.driftCount = (int) (sr * (0.2f + 0.4f * v.rng.uni()));
            }
            v.drift += (v.driftTarget - v.drift) * driftSmooth;
            v.vibRamp += (1.0f - v.vibRamp) * vibRampCoef;

            const float semis = v.pitch + bend + (v.drift + lfo * vibCents * v.vibRamp) * 0.01f;
            const float hz = 440.0f * std::exp2 ((semis - 69.0f) * (1.0f / 12.0f));

            v.o1.setFreq (hz * detDown, sr);
            v.o2.setFreq (hz * detUp, sr);
            v.sub.setFreq (hz * 0.5f, sr);

            float s1, q1, s2, q2;
            v.o1.next (s1, q1);
            v.o2.next (s2, q2);
            const float sub = v.sub.nextSquare();

            const float a = s1 + (q1 - s1) * f.shape;
            const float b = s2 + (q2 - s2) * f.shape;
            const float x = ((a + b * osc2Gain) * oscNorm * 0.5f + sub * f.depth * 0.42f) * 0.8f;

            // filtro: Tone + key tracking 50% + envolvente de velocity
            const float mod = v.fenv * coefs.fenvAmount + (v.pitch - 60.0f) * 0.5f;
            const float fc = std::clamp (baseCutoff * std::exp2 (mod * (1.0f / 12.0f)), 20.0f, maxFc);
            v.fenv *= fenvDecay;
            const float g = std::tan (pi * fc / sr);
            const float y = v.filt.process (x, g, k);

            // envolvente de amplitud
            if (! v.gate && ! v.sustained)
            {
                v.attacking = false;
                v.env *= coefs.releaseCoef;
                if (v.env < 0.0001f)
                {
                    v.active = false;
                    v.env = 0.0f;
                    continue;
                }
            }
            else if (v.attacking)
            {
                v.env += (1.25f - v.env) * coefs.attackCoef;
                if (v.env >= 1.0f) { v.env = 1.0f; v.attacking = false; }
            }

            out += y * v.env * (0.55f + 0.45f * v.vel);
        }
        return out;
    }

    bool anyActive() const
    {
        for (auto& v : voices) if (v.active) return true;
        return false;
    }

private:
    void startVoice (Voice& v, int note, float velocity, bool legato)
    {
        if (! v.active)
        {
            v.env = 0.0f;
            v.filt.reset();
            v.o1.phase = v.rng.uni();
            v.o2.phase = v.rng.uni();
            v.sub.phase = v.o1.phase * 0.5f;
            v.pitch = coefs.glideCoef < 1.0f && lastPitch >= 0.0f ? lastPitch : (float) note;
        }
        else if (coefs.glideCoef >= 1.0f)
            v.pitch = (float) note;

        v.note = note;
        v.target = (float) note;
        v.active = true;
        v.gate = true;
        v.sustained = false;
        v.stamp = ++stampCounter;

        if (! legato)
        {
            v.vel = velocity;
            v.attacking = true; // re-ataca desde el nivel actual: sin clicks
            v.fenv = velocity;
            v.vibRamp = 0.0f;
        }
    }

    void polyNoteOn (int note, float velocity)
    {
        Voice* chosen = nullptr;
        for (auto& v : voices) // misma nota sonando: re-usar
            if (v.active && v.note == note) { chosen = &v; break; }
        if (! chosen)
            for (auto& v : voices)
                if (! v.active) { chosen = &v; break; }
        if (! chosen) // robar la voz en release más vieja, si no la más vieja
        {
            for (auto& v : voices)
                if (! v.gate && ! v.sustained && (! chosen || v.stamp < chosen->stamp)) chosen = &v;
            if (! chosen)
                for (auto& v : voices)
                    if (! chosen || v.stamp < chosen->stamp) chosen = &v;
        }
        startVoice (*chosen, note, velocity, false);
    }

    void monoNoteOn (int note, float velocity)
    {
        // pila de notas apretadas
        removeHeld (note);
        if (heldCount < (int) held.size()) held[(size_t) heldCount++] = note;

        auto& v = voices[0];
        const bool legato = v.active && v.gate && heldCount > 1;
        startVoice (v, note, velocity, legato);
    }

    void monoNoteOff (int note)
    {
        removeHeld (note);
        auto& v = voices[0];
        if (! v.active || ! v.gate) return;
        if (heldCount > 0)
        {
            const int prev = held[(size_t) (heldCount - 1)];
            if (prev != v.note) startVoice (v, prev, v.vel, true);
        }
        else if (v.note == note)
        {
            v.gate = false;
            v.sustained = sustainPedal;
        }
    }

    void removeHeld (int note)
    {
        int j = 0;
        for (int i = 0; i < heldCount; ++i)
            if (held[(size_t) i] != note) held[(size_t) j++] = held[(size_t) i];
        heldCount = j;
    }

    std::array<Voice, maxVoices> voices;
    std::array<int, 32> held {};
    int heldCount = 0;
    bool mono = false, sustainPedal = false;
    float sr = 48000.0f, lfoPhase = 0.0f, bend = 0.0f, modWheel = 0.0f;
    float lastPitch = -1.0f;
    float fenvDecay = 0.999f, driftSmooth = 0.0001f, vibRampCoef = 0.0001f;
    uint32_t stampCounter = 0;
    BlockCoefs coefs;
};

} // namespace rcd
