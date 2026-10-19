# Piano sample attribution

The WAV files in `piano/` are trimmed, mono, loudness-normalised excerpts of the
piano multisamples from **tonejs-instruments**:

- Collection: <https://github.com/nbrosowsky/tonejs-instruments>
- Piano source: **VSCO 2 Community Edition** (Versilian Studios)
- License of the samples: **Creative Commons Attribution 3.0 Unported
  (CC-BY 3.0)** — <https://creativecommons.org/licenses/by/3.0/>
- Collection licence file: <https://github.com/nbrosowsky/tonejs-instruments/blob/master/LICENSE.md>

Modifications made for this project:

- kept one sample every three semitones (A1 … C8 instead of all notes),
- converted to mono 16-bit PCM at 44.1 kHz,
- removed leading silence, limited each sample to 5.5 s and added short fades,
- normalised each sample peak to 0.85.

The samples are distributed under CC-BY 3.0; the rest of Piano Waterfall is
MIT-licensed. If you redistribute a build, keep this file and the attribution in
the README / About dialog intact.
