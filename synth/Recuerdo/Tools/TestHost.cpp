// Host de prueba de Recuerdo: carga el VST3 compilado (igual que lo haría
// Ableton), renderiza cada preset a WAV y hace chequeos automáticos.
//
//   RecuerdoTestHost <ruta/Recuerdo.vst3> <carpeta_salida>

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_formats/juce_audio_formats.h>
#include <juce_dsp/juce_dsp.h>

#include <chrono>
#include <iostream>

using namespace juce;

namespace
{
constexpr double sampleRate = 48000.0;
constexpr int blockSize = 256;
int failures = 0;

void check (bool ok, const String& what)
{
    std::cout << (ok ? "  [OK]   " : "  [FAIL] ") << what << std::endl;
    if (! ok) ++failures;
}

struct Note { double start, length; int note; float vel; };

AudioProcessorParameter* findParam (AudioPluginInstance& p, const String& name)
{
    for (auto* prm : p.getParameters())
        if (prm->getName (64).equalsIgnoreCase (name)) return prm;
    return nullptr;
}

void setParam (AudioPluginInstance& p, const String& name, float plainValue)
{
    if (auto* prm = dynamic_cast<RangedAudioParameter*> (findParam (p, name)))
        prm->setValueNotifyingHost (prm->convertTo0to1 (plainValue));
    else if (auto* raw = findParam (p, name))
        raw->setValueNotifyingHost (plainValue);
}

// Renderiza notas; opcionalmente llama a `perBlock(sampleIndex)` antes de cada bloque.
AudioBuffer<float> render (AudioPluginInstance& p, const std::vector<Note>& notes, double seconds,
                           std::function<void (int64)> perBlock = {})
{
    const int total = (int) (seconds * sampleRate);
    AudioBuffer<float> out (2, total);
    AudioBuffer<float> block (2, blockSize);
    p.reset();

    for (int pos = 0; pos < total; pos += blockSize)
    {
        const int n = std::min (blockSize, total - pos);
        if (perBlock) perBlock (pos);

        MidiBuffer midi;
        for (auto& nt : notes)
        {
            const int on = (int) (nt.start * sampleRate), off = (int) ((nt.start + nt.length) * sampleRate);
            if (on >= pos && on < pos + n) midi.addEvent (MidiMessage::noteOn (1, nt.note, nt.vel), on - pos);
            if (off >= pos && off < pos + n) midi.addEvent (MidiMessage::noteOff (1, nt.note), off - pos);
        }
        block.setSize (2, n, false, false, true);
        block.clear();
        p.processBlock (block, midi);
        for (int c = 0; c < 2; ++c) out.copyFrom (c, pos, block, c, 0, n);
    }
    return out;
}

void writeWav (const AudioBuffer<float>& b, const File& f)
{
    f.deleteFile();
    WavAudioFormat wav;
    std::unique_ptr<AudioFormatWriter> w (wav.createWriterFor (new FileOutputStream (f), sampleRate, 2, 24, {}, 0));
    if (w) w->writeFromAudioSampleBuffer (b, 0, b.getNumSamples());
}

struct Stats { float peak = 0; double rms = 0; bool finite = true; };

Stats stats (const AudioBuffer<float>& b, int from = 0, int to = -1)
{
    if (to < 0) to = b.getNumSamples();
    Stats s; double acc = 0;
    for (int c = 0; c < b.getNumChannels(); ++c)
        for (int i = from; i < to; ++i)
        {
            const float x = b.getSample (c, i);
            if (! std::isfinite (x)) s.finite = false;
            s.peak = std::max (s.peak, std::abs (x));
            acc += (double) x * x;
        }
    s.rms = std::sqrt (acc / std::max (1, (to - from) * b.getNumChannels()));
    return s;
}

float db (double x) { return (float) Decibels::gainToDecibels (x, -200.0); }

// Energía bajo la fundamental (donde sólo puede haber aliasing) vs total.
float aliasRatioDb (const AudioBuffer<float>& b, int from, float f0)
{
    constexpr int order = 15, N = 1 << order;
    dsp::FFT fft (order);
    std::vector<float> data ((size_t) N * 2, 0.0f);
    dsp::WindowingFunction<float> win ((size_t) N, dsp::WindowingFunction<float>::blackmanHarris, false);
    for (int i = 0; i < N; ++i) data[(size_t) i] = b.getSample (0, from + i);
    win.multiplyWithWindowingTable (data.data(), (size_t) N);
    fft.performFrequencyOnlyForwardTransform (data.data());

    double below = 0, total = 0;
    for (int k = 1; k < N / 2; ++k)
    {
        const double hz = k * sampleRate / N, e = (double) data[(size_t) k] * data[(size_t) k];
        total += e;
        if (hz > 40.0 && hz < f0 * 0.85) below += e;
    }
    return db (std::sqrt (below / total));
}

// Mayor "salto" de muestra a muestra (2da diferencia), para detectar clicks.
float maxD2 (const AudioBuffer<float>& b, int from)
{
    float m = 0;
    for (int c = 0; c < 2; ++c)
        for (int i = std::max (from, 2); i < b.getNumSamples(); ++i)
            m = std::max (m, std::abs (b.getSample (c, i) - 2 * b.getSample (c, i - 1) + b.getSample (c, i - 2)));
    return m;
}

std::vector<Note> chords (double hold = 1.5, float vel = 0.8f)
{
    const int prog[4][4] = { { 48, 55, 59, 64 }, { 45, 52, 55, 60 }, { 41, 48, 52, 57 }, { 43, 50, 55, 59 } };
    std::vector<Note> v;
    for (int c = 0; c < 4; ++c)
        for (int n : prog[c]) v.push_back ({ 0.1 + c * 1.6, hold, n, vel });
    return v;
}

std::vector<Note> lead (int transpose = 0)
{
    // con solapamientos para probar legato/glide
    const int line[] = { 67, 69, 71, 74, 72, 71, 69, 67, 64, 67 };
    const double dur[] = { 0.5, 0.5, 0.5, 1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 1.5 };
    std::vector<Note> v;
    double t = 0.1;
    for (int i = 0; i < 10; ++i) { v.push_back ({ t, dur[i] + 0.05, line[i] + transpose, 0.85f }); t += dur[i]; }
    return v;
}

std::vector<Note> bassLine()
{
    const int line[] = { 36, 36, 43, 41, 36, 39, 41, 43 };
    std::vector<Note> v;
    for (int i = 0; i < 8; ++i) v.push_back ({ 0.1 + i * 0.4, 0.3, line[i], i % 2 ? 0.7f : 0.95f });
    v.push_back ({ 3.4, 1.5, 31, 0.9f });
    return v;
}

std::vector<Note> keys()
{
    std::vector<Note> v;
    const int prog[4][3] = { { 60, 64, 67 }, { 57, 60, 64 }, { 53, 57, 60 }, { 55, 59, 62 } };
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 2; ++r)
            for (int n : prog[c]) v.push_back ({ 0.1 + c * 0.9 + r * 0.45, 0.35, n, r ? 0.6f : 0.85f });
    return v;
}

std::vector<Note> arpeggio()
{
    std::vector<Note> v;
    const int notes[] = { 60, 64, 67, 71, 72, 71, 67, 64, 57, 60, 64, 67, 69, 67, 64, 60 };
    for (int i = 0; i < 16; ++i) v.push_back ({ 0.1 + i * 0.22, 0.2, notes[i], 0.75f });
    return v;
}
} // namespace

int main (int argc, char** argv)
{
    if (argc < 3) { std::cerr << "uso: RecuerdoTestHost <Recuerdo.vst3> <salida>\n"; return 2; }
    ScopedJuceInitialiser_GUI init;

    const File pluginFile (File::getCurrentWorkingDirectory().getChildFile (argv[1]));
    const File outDir (File::getCurrentWorkingDirectory().getChildFile (argv[2]));
    outDir.createDirectory();

    VST3PluginFormat format;
    OwnedArray<PluginDescription> types;
    format.findAllTypesForFile (types, pluginFile.getFullPathName());
    std::cout << "== Carga del VST3: " << pluginFile.getFullPathName() << std::endl;
    check (types.size() == 1, "el bundle expone exactamente 1 plugin");
    if (types.isEmpty()) return 1;

    const auto& desc = *types[0];
    std::cout << "  nombre=" << desc.name << "  fabricante=" << desc.manufacturerName
              << "  categoria=" << desc.category << "  instrumento=" << (desc.isInstrument ? "si" : "no") << std::endl;
    check (desc.isInstrument, "se registra como instrumento");

    String err;
    auto plugin = format.createInstanceFromDescription (desc, sampleRate, blockSize, err);
    check (plugin != nullptr, "instancia creada " + err);
    if (! plugin) return 1;

    plugin->setPlayConfigDetails (0, 2, sampleRate, blockSize);
    plugin->prepareToPlay (sampleRate, blockSize);
    check (plugin->acceptsMidi(), "acepta MIDI");

    std::cout << "  parametros (" << plugin->getParameters().size() << "):";
    int automatable = 0;
    for (auto* prm : plugin->getParameters())
    {
        if (prm->isAutomatable()) ++automatable;
        std::cout << " " << prm->getName (32);
    }
    std::cout << std::endl;
    check (findParam (*plugin, "Tone") && findParam (*plugin, "Space") && findParam (*plugin, "Mono"), "parametros principales visibles para el host");
    std::cout << "  automatizables: " << automatable << "  latencia: " << plugin->getLatencySamples() << " muestras" << std::endl;

    // --- Editor ---------------------------------------------------------------
    {
        std::unique_ptr<AudioProcessorEditor> ed (plugin->createEditorIfNeeded());
        check (ed != nullptr && ed->getWidth() > 0, "la interfaz se crea (" + String (ed ? ed->getWidth() : 0) + "x" + String (ed ? ed->getHeight() : 0) + ")");
        if (ed)
        {
            Image img (Image::ARGB, ed->getWidth(), ed->getHeight(), true);
            Graphics g (img);
            ed->paintEntireComponent (g, false);
            PNGImageFormat png;
            FileOutputStream os (outDir.getChildFile ("ui.png"));
            if (os.openedOk()) { os.setPosition (0); os.truncate(); png.writeImageToStream (img, os); }
        }
    }

    // --- Presets ----------------------------------------------------------------
    std::cout << "\n== Presets (" << plugin->getNumPrograms() << ")" << std::endl;
    check (plugin->getNumPrograms() == 8, "8 presets");
    for (int p = 0; p < plugin->getNumPrograms(); ++p)
    {
        plugin->setCurrentProgram (p);
        const auto name = plugin->getProgramName (p);
        std::vector<Note> notes;
        switch (p)
        {
            case 1: notes = lead(); break;
            case 2: notes = bassLine(); break;
            case 3: notes = keys(); break;
            case 6: notes = arpeggio(); break;
            case 7: notes = chords (0.6, 0.9f); break;
            default: notes = chords(); break;
        }
        auto t0 = std::chrono::steady_clock::now();
        auto buf = render (*plugin, notes, 9.0);
        const double secs = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        const auto s = stats (buf);
        const auto tail = stats (buf, buf.getNumSamples() - 4800);
        std::cout << "  " << String (p + 1) << ". " << name.paddedRight (' ', 22)
                  << " pico " << String (db (s.peak), 1) << " dBFS   rms " << String (db (s.rms), 1)
                  << " dB   cola " << String (db (tail.peak), 1) << " dB   CPU x" << String (juce::roundToInt (9.0 / secs)) << " tiempo real" << std::endl;
        check (s.finite, "  sin NaN/Inf");
        check (s.peak > 0.05f && s.peak < 1.0f, "  nivel razonable, sin clip");
        writeWav (buf, outDir.getChildFile (String (p + 1) + " - " + name + ".wav"));
    }

    // --- Aliasing ---------------------------------------------------------------
    std::cout << "\n== Aliasing (saw pura, filtro abierto, sin efectos)" << std::endl;
    plugin->setCurrentProgram (0);
    auto dry = [&] (float shape)
    {
        for (auto* n : { "Age", "Warmth", "Chorus", "Space", "Vibrato", "Detune", "Depth", "Glide" }) setParam (*plugin, n, 0.0f);
        setParam (*plugin, "Mono", 0.0f);
        setParam (*plugin, "Tone", 1.0f);
        setParam (*plugin, "Shape", shape);
        setParam (*plugin, "Attack", 0.001f);
        setParam (*plugin, "Volume", -6.0f);
    };
    for (float shape : { 0.0f, 1.0f })
        for (int note : { 84, 96, 103 })
        {
            dry (shape);
            const float f0 = 440.0f * std::pow (2.0f, (note - 69) / 12.0f);
            auto buf = render (*plugin, { { 0.0, 2.0, note, 1.0f } }, 1.5);
            const float r = aliasRatioDb (buf, 12000, f0);
            std::cout << "  " << (shape < 0.5f ? "saw   " : "square") << " nota " << note << " (" << String (f0, 0) << " Hz): energia alias bajo f0 = " << String (r, 1) << " dB" << std::endl;
            check (r < -45.0f, "  aliasing bajo (< -45 dB)");
        }

    // --- Clicks al mover perillas ---------------------------------------------
    std::cout << "\n== Suavizado: saltos bruscos de cada perilla mientras suena una nota" << std::endl;
    struct Jump { const char* name; float lo, hi; };
    const Jump jumps[] = { { "Tone", 0.05f, 0.95f }, { "Depth", 0.0f, 1.0f }, { "Age", 0.0f, 0.5f }, { "Warmth", 0.0f, 1.0f },
                           { "Detune", 0.0f, 1.0f }, { "Shape", 0.0f, 1.0f }, { "Chorus", 0.0f, 1.0f }, { "Vibrato", 0.0f, 1.0f },
                           { "Space", 0.0f, 1.0f }, { "Volume", -24.0f, 6.0f } };
    for (auto& j : jumps)
    {
        auto setup = [&]
        {
            dry (0.0f);
            setParam (*plugin, "Tone", 0.25f); // sonido oscuro: cualquier click resalta
            setParam (*plugin, "Volume", -12.0f);
        };
        const std::vector<Note> n { { 0.0, 10.0, 45, 0.9f } };
        setup(); setParam (*plugin, j.name, j.lo); const float a = maxD2 (render (*plugin, n, 1.5), 9600);
        setup(); setParam (*plugin, j.name, j.hi); const float b = maxD2 (render (*plugin, n, 1.5), 9600);
        setup();
        auto c = render (*plugin, n, 3.0, [&] (int64 pos) {
            if (pos >= 9600) setParam (*plugin, j.name, ((pos / 4800) % 2) ? j.hi : j.lo);
        });
        const float ratio = maxD2 (c, 9600) / std::max (a, b);
        std::cout << "  " << String (j.name).paddedRight (' ', 8) << " pico de salto relativo = " << String (ratio, 2) << std::endl;
        check (ratio < 1.6f, String ("  ") + j.name + " sin clicks");
    }

    // --- Estado (guardar/cargar proyecto) ---------------------------------------
    std::cout << "\n== Estado" << std::endl;
    plugin->setCurrentProgram (3);
    MemoryBlock state;
    plugin->getStateInformation (state);
    const float before = findParam (*plugin, "Age")->getValue();
    setParam (*plugin, "Age", 0.0f);
    plugin->setStateInformation (state.getData(), (int) state.getSize());
    check (std::abs (findParam (*plugin, "Age")->getValue() - before) < 1e-4f, "guardar/restaurar estado conserva las perillas");

    // --- CPU peor caso ---------------------------------------------------------
    {
        plugin->setCurrentProgram (5);
        std::vector<Note> many;
        for (int i = 0; i < 8; ++i) many.push_back ({ 0.0, 5.0, 48 + i * 3, 0.8f });
        auto t0 = std::chrono::steady_clock::now();
        render (*plugin, many, 5.0);
        const double secs = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        std::cout << "\n== CPU con 8 voces + todos los efectos: " << String (100.0 * secs / 5.0, 1) << " % de un nucleo" << std::endl;
    }

    plugin->releaseResources();
    plugin.reset();
    std::cout << "\n" << (failures == 0 ? "TODO OK" : String (failures) + " FALLAS") << std::endl;
    return failures == 0 ? 0 : 1;
}
