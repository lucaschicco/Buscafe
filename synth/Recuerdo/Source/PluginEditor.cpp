#include "PluginEditor.h"

namespace
{
const juce::Colour bg       { 0xff2b2420 };
const juce::Colour panel    { 0xff3a302a };
const juce::Colour cream    { 0xffeadcc3 };
const juce::Colour orange   { 0xffe0893c };
const juce::Colour dimText  { 0xffb8a58c };

// id, título: dos filas
const char* const row1[][2] = { { "tone", "TONE" }, { "depth", "DEPTH" }, { "detune", "DETUNE" }, { "shape", "SHAPE" },
                                { "warmth", "WARMTH" }, { "age", "AGE" }, { "chorus", "CHORUS" } };
const char* const row2[][2] = { { "vibrato", "VIBRATO" }, { "glide", "GLIDE" }, { "attack", "ATTACK" },
                                { "release", "RELEASE" }, { "space", "SPACE" }, { "volume", "VOLUME" } };
} // namespace

RecuerdoLookAndFeel::RecuerdoLookAndFeel()
{
    setColour (juce::Slider::textBoxTextColourId, dimText);
    setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour (juce::Label::textColourId, cream);
    setColour (juce::ComboBox::backgroundColourId, panel);
    setColour (juce::ComboBox::textColourId, cream);
    setColour (juce::ComboBox::outlineColourId, orange.withAlpha (0.6f));
    setColour (juce::ComboBox::arrowColourId, orange);
    setColour (juce::PopupMenu::backgroundColourId, panel);
    setColour (juce::PopupMenu::textColourId, cream);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, orange);
    setColour (juce::ToggleButton::textColourId, cream);
    setColour (juce::ToggleButton::tickColourId, orange);
    setColour (juce::ToggleButton::tickDisabledColourId, dimText);
}

void RecuerdoLookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos,
                                            float startAngle, float endAngle, juce::Slider&)
{
    auto bounds = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h).reduced (6.0f);
    const float radius = juce::jmin (bounds.getWidth(), bounds.getHeight()) * 0.5f;
    const auto c = bounds.getCentre();
    const float angle = startAngle + pos * (endAngle - startAngle);

    // arco de fondo y de valor
    juce::Path track, value;
    track.addCentredArc (c.x, c.y, radius, radius, 0.0f, startAngle, endAngle, true);
    value.addCentredArc (c.x, c.y, radius, radius, 0.0f, startAngle, angle, true);
    g.setColour (panel.brighter (0.15f));
    g.strokePath (track, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    g.setColour (orange);
    g.strokePath (value, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));

    // cuerpo de la perilla
    const float kr = radius * 0.78f;
    juce::ColourGradient grad (cream, c.x - kr * 0.5f, c.y - kr * 0.6f, cream.darker (0.55f), c.x + kr, c.y + kr, true);
    g.setGradientFill (grad);
    g.fillEllipse (c.x - kr, c.y - kr, kr * 2.0f, kr * 2.0f);
    g.setColour (juce::Colours::black.withAlpha (0.35f));
    g.drawEllipse (c.x - kr, c.y - kr, kr * 2.0f, kr * 2.0f, 1.5f);

    // indicador
    juce::Path pointer;
    pointer.addRoundedRectangle (-2.5f, -kr * 0.92f, 5.0f, kr * 0.45f, 2.0f);
    g.setColour (bg);
    g.fillPath (pointer, juce::AffineTransform::rotation (angle).translated (c.x, c.y));
}

//==============================================================================
RecuerdoEditor::RecuerdoEditor (RecuerdoProcessor& p) : AudioProcessorEditor (&p), proc (p)
{
    setLookAndFeel (&lnf);

    auto addKnob = [this] (const char* id, const char* title)
    {
        auto k = std::make_unique<Knob>();
        k->slider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
        k->slider.setTextBoxStyle (juce::Slider::TextBoxBelow, false, 90, 18);
        k->slider.setPopupDisplayEnabled (false, false, nullptr);
        k->slider.setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
        k->slider.setColour (juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
        k->label.setText (title, juce::dontSendNotification);
        k->label.setJustificationType (juce::Justification::centred);
        k->label.setFont (juce::FontOptions (15.0f, juce::Font::bold));
        addAndMakeVisible (k->slider);
        addAndMakeVisible (k->label);
        k->attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.apvts, id, k->slider);
        knobs.push_back (std::move (k));
    };
    for (auto& r : row1) addKnob (r[0], r[1]);
    for (auto& r : row2) addKnob (r[0], r[1]);

    for (int i = 0; i < proc.getNumPrograms(); ++i)
        presetBox.addItem (proc.getProgramName (i), i + 1);
    presetBox.setSelectedId (proc.getCurrentProgram() + 1, juce::dontSendNotification);
    presetBox.onChange = [this]
    {
        const int idx = presetBox.getSelectedId() - 1;
        if (idx >= 0 && idx != proc.getCurrentProgram())
        {
            proc.setCurrentProgram (idx);
            proc.updateHostDisplay (juce::AudioProcessor::ChangeDetails().withProgramChanged (true));
        }
    };
    addAndMakeVisible (presetBox);

    addAndMakeVisible (monoButton);
    monoAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (proc.apvts, "mono", monoButton);

    setSize (840, 470);
    startTimerHz (8);
}

RecuerdoEditor::~RecuerdoEditor() { setLookAndFeel (nullptr); }

void RecuerdoEditor::timerCallback()
{
    const int id = proc.getCurrentProgram() + 1;
    if (presetBox.getSelectedId() != id)
        presetBox.setSelectedId (id, juce::dontSendNotification);
}

void RecuerdoEditor::paint (juce::Graphics& g)
{
    g.fillAll (bg);

    auto header = getLocalBounds().removeFromTop (64).toFloat();
    g.setColour (panel);
    g.fillRect (header);
    g.setColour (orange);
    g.fillRect (header.removeFromBottom (3.0f));

    g.setColour (cream);
    g.setFont (juce::FontOptions (30.0f, juce::Font::bold));
    g.drawText ("RECUERDO", 24, 8, 300, 48, juce::Justification::centredLeft);
    g.setColour (dimText);
    g.setFont (juce::FontOptions (13.0f));
    g.drawText ("vintage synth", 196, 22, 160, 30, juce::Justification::centredLeft);
}

void RecuerdoEditor::resized()
{
    auto area = getLocalBounds();
    auto header = area.removeFromTop (64);
    monoButton.setBounds (header.removeFromRight (110).reduced (14, 18));
    presetBox.setBounds (header.removeFromRight (280).reduced (8, 16));

    area.reduce (14, 10);
    const int rowH = area.getHeight() / 2;

    auto layRow = [this] (juce::Rectangle<int> row, size_t first, size_t count)
    {
        const int w = row.getWidth() / 7;
        row = row.withSizeKeepingCentre (w * (int) count, row.getHeight());
        for (size_t i = 0; i < count; ++i)
        {
            auto cell = row.removeFromLeft (w).reduced (4);
            auto& k = *knobs[first + i];
            k.label.setBounds (cell.removeFromTop (22));
            k.slider.setBounds (cell);
        }
    };
    layRow (area.removeFromTop (rowH), 0, std::size (row1));
    layRow (area, std::size (row1), std::size (row2));
}
