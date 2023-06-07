import os
import math
import music21 as m21

TERM_SYMBOL = '.'
KERN_DATASET_PATH = './deutschl/erk'
SEQUENCE_LENGTH = 64
TIME_STEP = 0.25
HOLD_SYMBOL = '_'
#ACCEPTABLE_DURATIONS = [TIME_STEP*i for i in range(1, 33)]

def load_songs_in_kern(dataset_path: str) -> list[m21.stream.Score]:
    # go through all the files in the ds and load them with music21
    songs = []
    
    for path, subdirs, files in os.walk(dataset_path):
        for file in files:
            if str(file).endswith('.krn'):
                song = m21.converter.parse(os.path.join(path, file))
                songs.append(song)
    return songs

class Encoder:
    def __init__(self, time_step=TIME_STEP):
        self.time_step = time_step

    def transpose(self, song: m21.stream.Score) -> m21.stream.Score:
        # get key from the song
        parts = song.getElementsByClass(m21.stream.Part)
        measures_part0 = parts[0].getElementsByClass(m21.stream.Measure)
        key = measures_part0[0][4]

        # estimate key using music21
        if not isinstance(key, m21.key.Key):
            key = song.analyse('key')

        # get interval for transposition, e.g., Bmaj -> Cmaj
        if key.mode == 'major':
            interval = m21.interval.Interval(key.tonic, m21.pitch.Pitch('C'))
        elif key.mode == 'minor':
            interval = m21.interval.Interval(key.tonic, m21.pitch.Pitch('A'))

        # transpose song by calculated interval
        transpose_song = song.transpose(interval)

        return transpose_song
    
    def encode_songs(self, songs: list[m21.stream.Score], transpose_to_major=True, flatten=False, terminal=False) -> list[list[str]]:
        encoded_songs = []
        invalid_song_indices = []
        for i, song in enumerate(songs):
            # filter out songs that have non-acceptalbe durations
            if not self.has_acceptable_duration(song):
                invalid_song_indices.append(i)
                continue
            
            # transpose songs to Cmaj/Amin
            if transpose_to_major:
                song = self.transpose(song)
            
            
            # encode songs with music time series representation
            encoded_song = self.encode_song(song)
            if terminal:
                    encoded_song = [TERM_SYMBOL] + encoded_song
            if flatten:
                encoded_songs += encoded_song
            else:
                encoded_songs.append(encoded_song)
        return encoded_songs, invalid_song_indices
    
    def decode_songs(self, melodies: list[list[str]]) -> list[m21.stream.Score]:
        songs = []
        for melody in melodies:
            songs.append(self.decode_song(melody))
        return songs
    
    def __is_float_close_to_int(self, n, tolerance=1e-5):
        closest_int = round(n)
        return math.isclose(n, closest_int, abs_tol=tolerance)
    
    def has_acceptable_duration(self, song: m21.stream.Score) -> bool:
        scale = self.time_step / 0.25  # 1/8 / 1/4 = 4/8 = 0.5
        for note in song.flat.notesAndRests:
            if not self.__is_float_close_to_int(note.duration.quarterLength / scale):
                return False
        return True
        
    def encode_song(self, song: m21.stream.Score) -> list[str]:
        pass

    def decode_song(self, melody: list[str]) -> m21.stream.Stream:
        pass
    
    def take_notes(self, melody: list[str], n_notes: int) -> list[str]:
        pass

class GridEncoder(Encoder):
    """
    Encoder that encode each single beat, meaning that each token represents the exact same amount of time.
    One can also say this encoding is equitemporal.
    """

    def __init__(self, time_step=TIME_STEP):
        super().__init__(time_step)
        self.time_step = time_step
    
    def encode_song(self, song : m21.stream.Score) -> list[str]:
        # p = 60, d = 1.0 -> [60, "_", "_", "_"]
        
        encoded_song = []
        
        for event in song.flat.notesAndRests:
            
            # handle notes
            if isinstance(event, m21.note.Note):
                symbol = event.pitch.midi # e.g. 60
            
            #handle rests
            elif isinstance(event, m21.note.Rest):
                symbol = 'r'
            
            # convert the note/rest into time series notation
            steps = int(event.duration.quarterLength / (self.time_step/0.25))
            for step in range(steps):
                if step == 0:
                    encoded_song.append(str(symbol))
                else:
                    encoded_song.append(HOLD_SYMBOL)
                    
        #encoded_song = ' '.join(map(str, encoded_song))
        
        return encoded_song

    def decode_song(self, melody: list[str]) -> m21.stream.Stream:

        # create a music21 stream
        stream = m21.stream.Stream()

        # parse all the symbols in the melody and create note/rest objects
        start_symbol = None
        step_counter = 1

        for i, symbol in enumerate(melody):
            if symbol != HOLD_SYMBOL or i + 1 == len(melody):

                if start_symbol is not None:
                    quater_length_duration = (self.time_step/0.25) * step_counter

                    if start_symbol == 'r':
                        m21_event = m21.note.Rest()

                    else:
                        m21_event = m21.note.Note(int(start_symbol))

                    dur = m21.duration.Duration()
                    dur.quarterLength = quater_length_duration
                    m21_event.duration = dur
                    stream.append(m21_event)

                    # reset the step counter
                    step_counter = 1

                start_symbol = symbol
            else:
                step_counter += 1
        return stream
    
    def take_notes(self, melody: list[str], n_notes: int) -> list[str]:
        part = []
        note_count = 0
        for symbol in melody:
            
            if symbol != HOLD_SYMBOL:
                if note_count >= n_notes:
                    break
                note_count += 1
            part.append(symbol)
            
        return part
    
class NoteEncoder(Encoder):
    """
    Encoder that encode each single note, meaning that each token represents one note (of different length/duration).
    One can also say this encoding is not equitemporal.
    """

    def __init__(self, time_step=TIME_STEP):
        super().__init__(time_step)
        self.time_step = time_step

    def encode_song(self, song: m21.stream.Score) -> list[str]:
        # p = 60, d = 1.0 -> 60/4 assuming 0.25 min duration

        encoded_song = []

        for event in song.flat.notesAndRests:

            # handle notes
            if isinstance(event, m21.note.Note):
                symbol = event.pitch.midi  # e.g. 60

            # handle rests
            elif isinstance(event, m21.note.Rest):
                symbol = 'r'

            # convert the note/rest into time series notation
            steps = int(round(event.duration.quarterLength / (self.time_step/0.25)))
            encoded_song.append(str(symbol)+'/'+str(steps))
        return encoded_song
            
    def decode_song(self, melody: list[str]) -> m21.stream.Stream:
        # create a music21 stream
        stream = m21.stream.Stream()

        for i, symbol in enumerate(melody):

            split = symbol.split('/')
            pitch, steps = split[0], split[1]

            if pitch == 'r':
                m21_event = m21.note.Rest()
            else:
                m21_event = m21.note.Note(int(pitch))

            dur = m21.duration.Duration()
            dur.quarterLength = (self.time_step/0.25)*int(steps)
            m21_event.duration = dur
            
            stream.append(m21_event)
        return stream

    def take_notes(self, melody: list[str], n_notes: int) -> list[str]:
        return melody[:min(n_notes, len(melody))]

class StringToIntEncoder:
    def __init__(self, enc_songs: list[list[str]]):
        self.symbols = sorted(
            list(set([item for sublist in enc_songs for item in sublist])))
        
        self.stoi = {s: i+1 for i, s in enumerate(self.symbols)}
        self.stoi[TERM_SYMBOL] = 0
        self.itos = {i: s for s, i in self.stoi.items()}

    def __len__(self) -> int:
        return len(self.stoi)

    def encode(self, symbol: str) -> int:
        return self.stoi[symbol]
    
    def decode(self, index: int) -> str:
        return self.itos[index]