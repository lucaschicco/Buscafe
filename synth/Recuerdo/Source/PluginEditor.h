#pragma once

#include "PluginProcessor.h"

class RecuerdoLookAndFeel : public juce::LookAndFeel_V4
{
public:
    RecuerdoLookAndFeel();
    void drawRotarySlider (juce::Graphics&, int x, int y, int w, int h, float pos,
                           float startAngle, float endAngle, juce::Slider&) override;
};

class RecuerdoEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit RecuerdoEditor (RecuerdoProcessor&);
    ~RecuerdoEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    void timerCallback() override;

    struct Knob
    {
        juce::Slider slider;
        juce::Label label;
        std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> attachment;
    };

    RecuerdoProcessor& proc;
    RecuerdoLookAndFeel lnf;
    std::vector<std::unique_ptr<Knob>> knobs;
    juce::ComboBox presetBox;
    juce::ToggleButton monoButton { "Mono" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> monoAttachment;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (RecuerdoEditor)
};
