#include "PluginProcessor.h"
#include "PluginEditor.h"

namespace
{
juce::String pct (float v, int) { return juce::String (juce::roundToInt (v * 100.0f)) + " %"; }

juce::String seconds (float v, int)
{
    if (v < 1.0f) return juce::String (juce::roundToInt (v * 1000.0f)) + " ms";
    return juce::String (v, 2) + " s";
}

juce::NormalisableRange<float> timeRange (float lo, float hi, float centre)
{
    juce::NormalisableRange<float> r (lo, hi);
    r.setSkewForCentre (centre);
    return r;
}
} // namespace

//==============================================================================
const std::vector<RecuerdoPreset>& RecuerdoProcessor::presets()
{
    //                name                   tone  depth age   warm  detun shape chor  vib   glide mono   att    rel   space vol(dB)
    static const std::vector<RecuerdoPreset> list {
        { "Pad Nost\xc3\xa1lgico",           0.45f, 0.30f, 0.35f, 0.30f, 0.45f, 0.10f, 0.70f, 0.05f, 0.00f, false, 0.90f, 2.50f, 0.55f, -4.0f },
        { "Lead Tame Impala",                0.62f, 0.25f, 0.30f, 0.55f, 0.30f, 0.35f, 0.55f, 0.30f, 0.12f, true,  0.01f, 0.35f, 0.35f, -4.0f },
        { "Bajo Oscuro",                     0.28f, 0.80f, 0.15f, 0.50f, 0.15f, 0.50f, 0.00f, 0.00f, 0.05f, true,  0.003f, 0.15f, 0.05f, -3.0f },
        { "Keys de Cinta Vieja",             0.50f, 0.20f, 0.60f, 0.35f, 0.20f, 0.60f, 0.40f, 0.00f, 0.00f, false, 0.004f, 0.90f, 0.35f, -4.0f },
        { "Cuerdas Juno",                    0.55f, 0.15f, 0.20f, 0.25f, 0.55f, 0.00f, 0.85f, 0.08f, 0.00f, false, 0.50f, 1.80f, 0.45f, -5.0f },
        { "VHS Roto",                        0.40f, 0.35f, 0.95f, 0.60f, 0.50f, 0.30f, 0.50f, 0.00f, 0.00f, false, 0.20f, 1.50f, 0.50f, -4.0f },
        { "Keys Atardecer",                  0.42f, 0.20f, 0.25f, 0.30f, 0.25f, 0.20f, 0.60f, 0.00f, 0.00f, false, 0.002f, 0.60f, 0.45f, -4.0f },
        { "Brass Ochentoso",                 0.58f, 0.30f, 0.10f, 0.45f, 0.40f, 0.00f, 0.30f, 0.06f, 0.00f, false, 0.06f, 0.40f, 0.25f, -5.0f },
    };
    return list;
}

juce::AudioProcessorValueTreeState::ParameterLayout RecuerdoProcessor::createLayout()
{
    using namespace juce;
    AudioProcessorValueTreeState::ParameterLayout layout;

    auto unit = [&] (const char* id, const char* name, float def)
    {
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { id, 1 }, name,
                                                           NormalisableRange<float> (0.0f, 1.0f), def,
                                                           AudioParameterFloatAttributes().withStringFromValueFunction (pct)));
    };

    unit ("tone",    "Tone",    0.5f);
    unit ("depth",   "Depth",   0.3f);
    unit ("age",     "Age",     0.3f);
    unit ("warmth",  "Warmth",  0.3f);
    unit ("detune",  "Detune",  0.3f);
    unit ("shape",   "Shape",   0.0f);
    unit ("chorus",  "Chorus",  0.5f);
    unit ("vibrato", "Vibrato", 0.0f);

    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "glide", 1 }, "Glide", timeRange (0.0f, 1.0f, 0.15f), 0.0f,
                                                       AudioParameterFloatAttributes().withStringFromValueFunction (seconds)));
    layout.add (std::make_unique<AudioParameterBool> (ParameterID { "mono", 1 }, "Mono", false));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "attack", 1 }, "Attack", timeRange (0.001f, 5.0f, 0.15f), 0.01f,
                                                       AudioParameterFloatAttributes().withStringFromValueFunction (seconds)));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "release", 1 }, "Release", timeRange (0.005f, 8.0f, 0.6f), 0.5f,
                                                       AudioParameterFloatAttributes().withStringFromValueFunction (seconds)));
    unit ("space", "Space", 0.3f);
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "volume", 1 }, "Volume", NormalisableRange<float> (-24.0f, 6.0f), -4.0f,
                                                       AudioParameterFloatAttributes()
                                                           .withStringFromValueFunction ([] (float v, int) { return String (v, 1) + " dB"; })
                                                           .withLabel ("dB")));
    return layout;
}

//==============================================================================
RecuerdoProcessor::RecuerdoProcessor()
    : AudioProcessor (BusesProperties().withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "RecuerdoState", createLayout())
{
    pTone    = apvts.getRawParameterValue ("tone");
    pDepth   = apvts.getRawParameterValue ("depth");
    pAge     = apvts.getRawParameterValue ("age");
    pWarmth  = apvts.getRawParameterValue ("warmth");
    pDetune  = apvts.getRawParameterValue ("detune");
    pShape   = apvts.getRawParameterValue ("shape");
    pChorus  = apvts.getRawParameterValue ("chorus");
    pVibrato = apvts.getRawParameterValue ("vibrato");
    pGlide   = apvts.getRawParameterValue ("glide");
    pMono    = apvts.getRawParameterValue ("mono");
    pAttack  = apvts.getRawParameterValue ("attack");
    pRelease = apvts.getRawParameterValue ("release");
    pSpace   = apvts.getRawParameterValue ("space");
    pVolume  = apvts.getRawParameterValue ("volume");

    setCurrentProgram (0);
}

bool RecuerdoProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto out = layouts.getMainOutputChannelSet();
    return out == juce::AudioChannelSet::stereo() || out == juce::AudioChannelSet::mono();
}

void RecuerdoProcessor::prepareToPlay (double sampleRate, int /*samplesPerBlock*/)
{
    sr = sampleRate;
    engine.prepare (sampleRate);
    chorus.prepare ((float) sampleRate);
    tape.prepare ((float) sampleRate);
    dc.prepare ((float) sampleRate);
    reverb.setSampleRate (sampleRate);
    reverb.reset();

    oversampler.reset();
    oversampler.initProcessing (chunkSize);
    setLatencySamples (juce::roundToInt (oversampler.getLatencyInSamples()));

    mono.setSize (1, chunkSize, false, true, true);

    const double ramp = 0.04;
    for (auto* s : { &sTone, &sDepth, &sAge, &sWarmth, &sDetune, &sShape, &sChorus, &sVibrato, &sSpace, &sGain })
        s->reset (sampleRate, ramp);

    sTone.setCurrentAndTargetValue (*pTone);
    sDepth.setCurrentAndTargetValue (*pDepth);
    sAge.setCurrentAndTargetValue (*pAge);
    sWarmth.setCurrentAndTargetValue (*pWarmth);
    sDetune.setCurrentAndTargetValue (*pDetune);
    sShape.setCurrentAndTargetValue (*pShape);
    sChorus.setCurrentAndTargetValue (*pChorus);
    sVibrato.setCurrentAndTargetValue (*pVibrato);
    sSpace.setCurrentAndTargetValue (*pSpace);
    sGain.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (pVolume->load()));
}

void RecuerdoProcessor::handleMidi (const juce::MidiMessage& m)
{
    if (m.isNoteOn())
        engine.noteOn (m.getNoteNumber(), m.getFloatVelocity());
    else if (m.isNoteOff())
        engine.noteOff (m.getNoteNumber());
    else if (m.isPitchWheel())
        engine.setPitchBend ((float) (m.getPitchWheelValue() - 8192) / 8192.0f * 2.0f);
    else if (m.isSustainPedalOn())
        engine.setSustain (true);
    else if (m.isSustainPedalOff())
        engine.setSustain (false);
    else if (m.isControllerOfType (1))
        engine.setModWheel ((float) m.getControllerValue() / 127.0f);
    else if (m.isAllNotesOff() || m.isAllSoundOff())
        engine.allNotesOff();
}

void RecuerdoProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;

    sTone.setTargetValue (*pTone);
    sDepth.setTargetValue (*pDepth);
    sAge.setTargetValue (*pAge);
    sWarmth.setTargetValue (*pWarmth);
    sDetune.setTargetValue (*pDetune);
    sShape.setTargetValue (*pShape);
    sChorus.setTargetValue (*pChorus);
    sVibrato.setTargetValue (*pVibrato);
    sSpace.setTargetValue (*pSpace);
    sGain.setTargetValue (juce::Decibels::decibelsToGain (pVolume->load()));

    engine.setBlockParams (*pAttack, *pRelease, *pGlide, *pMono > 0.5f);

    const int total = buffer.getNumSamples();
    for (int start = 0; start < total; start += chunkSize)
        renderChunk (buffer, midi, start, std::min (chunkSize, total - start));
}

void RecuerdoProcessor::renderChunk (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi, int start, int num)
{
    float* m = mono.getWritePointer (0);
    const int end = start + num;

    // --- voces, intercalando eventos MIDI en su posición exacta -------------
    auto it = midi.findNextSamplePosition (start);
    rcd::Frame f;
    for (int i = start; i < end; ++i)
    {
        while (it != midi.cend() && (*it).samplePosition <= i)
        {
            handleMidi ((*it).getMessage());
            ++it;
        }
        f.tone = sTone.getNextValue();
        f.depth = sDepth.getNextValue();
        f.detune = sDetune.getNextValue();
        f.shape = sShape.getNextValue();
        f.vibrato = sVibrato.getNextValue();

        const int j = i - start;
        m[j] = engine.renderSample (f);
        warmthArr[(size_t) j] = sWarmth.getNextValue();
        chorusArr[(size_t) j] = sChorus.getNextValue();
        ageArr[(size_t) j] = sAge.getNextValue();
        gainArr[(size_t) j] = sGain.getNextValue();
    }

    // --- Warmth: saturación sobremuestreada 2x ------------------------------
    {
        juce::dsp::AudioBlock<float> block (mono);
        auto sub = block.getSubBlock (0, (size_t) num);
        auto up = oversampler.processSamplesUp (sub);
        float* u = up.getChannelPointer (0);
        const int n = (int) up.getNumSamples();
        for (int j = 0; j < n; ++j)
            u[j] = rcd::warmthShape (u[j], warmthArr[(size_t) (j >> 1)]);
        oversampler.processSamplesDown (sub);
    }

    // --- Chorus (mono -> estéreo) -------------------------------------------
    float* L = buffer.getWritePointer (0, start);
    float* R = buffer.getNumChannels() > 1 ? buffer.getWritePointer (1, start) : nullptr;
    float tmpR[chunkSize];
    float* r = R != nullptr ? R : tmpR;

    for (int j = 0; j < num; ++j)
        chorus.process (dc.process (m[j]), chorusArr[(size_t) j], L[j], r[j]);

    // --- Space: reverb ------------------------------------------------------
    const float space = sSpace.getNextValue();
    sSpace.skip (num - 1);
    juce::Reverb::Parameters rp;
    rp.roomSize = 0.55f + 0.42f * space;
    rp.damping = 0.55f;
    rp.wetLevel = 0.42f * space;
    rp.dryLevel = 0.5f * (1.0f - 0.35f * space);
    rp.width = 1.0f;
    reverb.setParameters (rp);
    reverb.processStereo (L, r, num);

    // --- Age: cinta + volumen ------------------------------------------------
    for (int j = 0; j < num; ++j)
    {
        float l = L[j], rr = r[j];
        tape.process (l, rr, ageArr[(size_t) j]);
        const float g = gainArr[(size_t) j];
        L[j] = l * g;
        r[j] = rr * g;
    }

    if (R == nullptr)
        for (int j = 0; j < num; ++j) L[j] = 0.5f * (L[j] + r[j]);
}

//==============================================================================
int RecuerdoProcessor::getNumPrograms() { return (int) presets().size(); }

const juce::String RecuerdoProcessor::getProgramName (int index)
{
    if (juce::isPositiveAndBelow (index, (int) presets().size()))
        return juce::String::fromUTF8 (presets()[(size_t) index].name);
    return {};
}

void RecuerdoProcessor::setCurrentProgram (int index)
{
    if (! juce::isPositiveAndBelow (index, (int) presets().size())) return;
    currentProgram = index;
    const auto& p = presets()[(size_t) index];

    auto set = [this] (const char* id, float value)
    {
        if (auto* param = apvts.getParameter (id))
            param->setValueNotifyingHost (param->convertTo0to1 (value));
    };
    set ("tone", p.tone);
    set ("depth", p.depth);
    set ("age", p.age);
    set ("warmth", p.warmth);
    set ("detune", p.detune);
    set ("shape", p.shape);
    set ("chorus", p.chorus);
    set ("vibrato", p.vibrato);
    set ("glide", p.glide);
    set ("mono", p.mono ? 1.0f : 0.0f);
    set ("attack", p.attack);
    set ("release", p.release);
    set ("space", p.space);
    set ("volume", p.volume);
}

void RecuerdoProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    state.setProperty ("program", currentProgram, nullptr);
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void RecuerdoProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
        {
            auto tree = juce::ValueTree::fromXml (*xml);
            currentProgram = (int) tree.getProperty ("program", 0);
            apvts.replaceState (tree);
        }
}

juce::AudioProcessorEditor* RecuerdoProcessor::createEditor() { return new RecuerdoEditor (*this); }

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() { return new RecuerdoProcessor(); }
