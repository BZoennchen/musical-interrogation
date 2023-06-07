# the following is to play music on google colab
from music21 import *
from midi2audio import FluidSynth

def score_to_wav(score, filename):
    mf = midi.translate.streamToMidiFile(score)
    mf.open('music.mid', 'wb')
    mf.write()
    mf.close()
    # Convert midi to audio
    FluidSynth().midi_to_audio('music.mid', filename)

    # Play the audio file
    return filename