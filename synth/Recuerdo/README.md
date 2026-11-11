# Recuerdo — sinte vintage (VST3 / AU)

Sinte polifónico de 8 voces con sonido "Juno + cinta vieja", hecho con JUCE 8.

| Perilla | Qué hace |
|---|---|
| **Tone** | Filtro ladder lowpass 4 polos (60 Hz – 20 kHz) con algo de resonancia, key tracking y un leve "pluck" por velocity en ataques cortos |
| **Depth** | Sub-oscilador cuadrado una octava abajo |
| **Detune** | Dos osciladores PolyBLEP desafinados entre sí (0 – 40 cents) |
| **Shape** | Forma de onda: saw ↔ square |
| **Warmth** | Saturación analógica asimétrica, sobremuestreada 2x |
| **Age** | Cinta: wow/flutter + deriva aleatoria de pitch, pérdida de agudos, hiss (sólo mientras suena) y, por encima de ~60 %, cortes de nivel |
| **Chorus** | Chorus estéreo estilo Juno (BBD con LFO triangular en contrafase) |
| **Vibrato** | Vibrato 5.3 Hz con entrada gradual por nota (el mod wheel también suma) |
| **Glide** | Portamento; en modo **Mono** hace legato |
| **Attack / Release** | Envolvente de amplitud |
| **Space** | Reverb |
| **Volume** | Nivel de salida |

Todas las perillas son automatizables y están suavizadas (sin clicks). También responde a pitch bend (±2), mod wheel y pedal de sustain.

## Presets
1. Pad Nostálgico · 2. Lead Tame Impala · 3. Bajo Oscuro · 4. Keys de Cinta Vieja · 5. Cuerdas Juno · 6. VHS Roto · 7. Keys Atardecer · 8. Brass Ochentoso

## Descargar ya compilado
Cada push que toca `synth/Recuerdo/` dispara el workflow **Recuerdo synth (VST3)** en GitHub Actions, que compila para macOS (universal, Apple Silicon + Intel) y Windows. Los zips quedan en la pestaña *Actions* → el run → *Artifacts*.

### Instalar
- **macOS**: descomprimí y copiá `Recuerdo.vst3` a `~/Library/Audio/Plug-Ins/VST3/` (y opcionalmente `Recuerdo.component` a `~/Library/Audio/Plug-Ins/Components/`). Como no está firmado con certificado de Apple, la primera vez corré en Terminal:
  `xattr -dr com.apple.quarantine ~/Library/Audio/Plug-Ins/VST3/Recuerdo.vst3`
- **Windows**: descomprimí y copiá la carpeta `Recuerdo.vst3` a `C:\Program Files\Common Files\VST3\`.

En Ableton: *Preferencias → Plug-ins* → activar "Use VST3 Plug-in System Folders" → *Rescan*. Aparece en *Plug-ins → VST3 → Recuerdo Audio*.

## Compilar a mano
Requiere CMake ≥ 3.22 y Xcode (Mac) o Visual Studio 2022 (Windows).

```sh
cd synth/Recuerdo
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```
El plugin queda en `build/Recuerdo_artefacts/Release/VST3/Recuerdo.vst3`.

### Host de prueba
`-DRECUERDO_BUILD_TESTHOST=ON` compila `RecuerdoTestHost`, que carga el `.vst3` igual que un DAW, renderiza cada preset a WAV y chequea aliasing, clicks al mover perillas, NaN, nivel, guardado de estado y CPU:

```sh
./build/RecuerdoTestHost_artefacts/Release/RecuerdoTestHost build/Recuerdo_artefacts/Release/VST3/Recuerdo.vst3 renders
```

## Código
- `Source/DSP.h` — osciladores PolyBLEP, ladder ZDF, chorus Juno, etapa de cinta, saturación
- `Source/SynthEngine.h` — voces, poly/mono, glide, envolventes
- `Source/PluginProcessor.*` — parámetros, presets, cadena de efectos (voces → warmth → chorus → reverb → cinta)
- `Source/PluginEditor.*` — interfaz
