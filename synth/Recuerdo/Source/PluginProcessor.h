#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_utils/juce_audio_utils.h>
#include <juce_dsp/juce_dsp.h>

#include "DSP.h"
#include "SynthEngine.h"

struct RecuerdoPreset
{
    const char* name;
    float tone, depth, age, warmth, detune, shape, chorus, vibrato, glide;
    bool mono;
    float attack, release, space, volume;
};

class RecuerdoProcessor : public juce::AudioProcessor
{
public:
    RecuerdoProcessor();
    ~RecuerdoProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    using AudioProcessor::processBlock;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 8.0; }

    int getNumPrograms() override;
    int getCurrentProgram() override { return currentProgram; }
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    static juce::AudioProcessorValueTreeState::ParameterLayout createLayout();
    static const std::vector<RecuerdoPreset>& presets();

    juce::AudioProcessorValueTreeState apvts;

private:
    void handleMidi (const juce::MidiMessage& m);
    void renderChunk (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi, int start, int num);

    rcd::SynthEngine engine;
    rcd::JunoChorus chorus;
    rcd::TapeStage tape;
    rcd::DcBlocker dc;
    juce::Reverb reverb;
    juce::dsp::Oversampling<float> oversampler { 1, 1, juce::dsp::Oversampling<float>::filterHalfBandPolyphaseIIR, true, false };

    using Smooth = juce::SmoothedValue<float, juce::ValueSmoothingTypes::Linear>;
    Smooth sTone, sDepth, sAge, sWarmth, sDetune, sShape, sChorus, sVibrato, sSpace, sGain;

    std::atomic<float>* pTone {};
    std::atomic<float>* pDepth {};
    std::atomic<float>* pAge {};
    std::atomic<float>* pWarmth {};
    std::atomic<float>* pDetune {};
    std::atomic<float>* pShape {};
    std::atomic<float>* pChorus {};
    std::atomic<float>* pVibrato {};
    std::atomic<float>* pGlide {};
    std::atomic<float>* pMono {};
    std::atomic<float>* pAttack {};
    std::atomic<float>* pRelease {};
    std::atomic<float>* pSpace {};
    std::atomic<float>* pVolume {};

    static constexpr int chunkSize = 512;
    juce::AudioBuffer<float> mono;
    std::array<float, chunkSize> warmthArr {}, chorusArr {}, ageArr {}, gainArr {};

    double sr = 48000.0;
    int currentProgram = 0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (RecuerdoProcessor)
};
