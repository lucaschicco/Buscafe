cmake_minimum_required(VERSION 3.22)

project(Recuerdo VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# JUCE se descarga solo. Para usar una copia local:
#   cmake -B build -DFETCHCONTENT_SOURCE_DIR_JUCE=/ruta/a/JUCE
include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        8.0.4
    GIT_SHALLOW    ON)
FetchContent_MakeAvailable(JUCE)

juce_add_plugin(Recuerdo
    COMPANY_NAME                "Recuerdo Audio"
    PLUGIN_MANUFACTURER_CODE    Rcdo
    PLUGIN_CODE                 Rcd1
    FORMATS                     VST3 AU Standalone
    PRODUCT_NAME                "Recuerdo"
    IS_SYNTH                    TRUE
    NEEDS_MIDI_INPUT            TRUE
    NEEDS_MIDI_OUTPUT           FALSE
    IS_MIDI_EFFECT              FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD     FALSE
    VST3_CATEGORIES             Instrument Synth
    BUNDLE_ID                   com.recuerdoaudio.recuerdo)

target_sources(Recuerdo PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp)

target_compile_definitions(Recuerdo PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

if(MSVC)
    target_compile_options(Recuerdo PRIVATE /utf-8)
endif()

target_link_libraries(Recuerdo
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)

# Host de prueba: carga el .vst3, renderiza cada preset a WAV y chequea
# silencio/NaN/aliasing/clicks. Sólo para desarrollo.
option(RECUERDO_BUILD_TESTHOST "Compilar el host de prueba" OFF)
if(RECUERDO_BUILD_TESTHOST)
    juce_add_console_app(RecuerdoTestHost PRODUCT_NAME "RecuerdoTestHost")
    target_sources(RecuerdoTestHost PRIVATE Tools/TestHost.cpp)
    target_compile_definitions(RecuerdoTestHost PRIVATE
        JUCE_PLUGINHOST_VST3=1 JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
    target_link_libraries(RecuerdoTestHost PRIVATE
        juce::juce_audio_processors juce::juce_audio_formats juce::juce_dsp
        PUBLIC juce::juce_recommended_config_flags)
endif()
