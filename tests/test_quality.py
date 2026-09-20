import unittest

import numpy as np

from audio import SAMPLE_RATE, analyze, normalize, speech_level_db
from diarization import label_segments
from transcription import Segment, group_paragraphs


def tone(seconds, amplitude):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class AudioTests(unittest.TestCase):
    def test_quiet_audio_is_raised_without_clipping(self):
        audio = np.concatenate([tone(2, 0.005), np.zeros(SAMPLE_RATE * 3, np.float32)])
        result = normalize(audio)
        self.assertGreater(speech_level_db(result), speech_level_db(audio) + 10)
        self.assertLessEqual(float(np.max(np.abs(result))), 0.98 + 1e-6)

    def test_loud_audio_never_exceeds_peak_limit(self):
        result = normalize(tone(1, 0.99) + 0.005)
        self.assertLessEqual(float(np.max(np.abs(result))), 0.98 + 1e-6)

    def test_silence_and_empty_are_left_alone(self):
        self.assertEqual(float(np.max(np.abs(normalize(np.zeros(16000, np.float32))))), 0.0)
        self.assertEqual(len(normalize(np.zeros(0, np.float32))), 0)

    def test_warnings(self):
        self.assertTrue(analyze(np.zeros(16000, np.float32)))
        self.assertTrue(any("bajo" in w for w in analyze(tone(1, 0.005))))
        self.assertTrue(any("saturado" in w for w in analyze(np.clip(tone(1, 3), -1, 1))))
        self.assertEqual(analyze(tone(1, 0.1)), [])


class ParagraphTests(unittest.TestCase):
    def test_joins_close_segments_and_splits_on_pause_or_speaker(self):
        segments = [
            Segment(0, 2, "Hola."),
            Segment(2.2, 4, "¿Qué tal?"),
            Segment(9, 10, "Después de una pausa."),
            Segment(10.1, 11, "Otra voz.", speaker="Speaker 2"),
        ]
        result = group_paragraphs(segments)
        self.assertEqual(
            [(p.start, p.end, p.text, p.speaker) for p in result],
            [
                (0, 4, "Hola. ¿Qué tal?", None),
                (9, 10, "Después de una pausa.", None),
                (10.1, 11, "Otra voz.", "Speaker 2"),
            ],
        )

    def test_long_paragraph_breaks_at_sentence_end(self):
        segments = [
            Segment(i, i + 0.9, f"Esta es la frase de prueba número {i} del párrafo largo.")
            for i in range(20)
        ]
        result = group_paragraphs(segments)
        self.assertGreater(len(result), 1)
        self.assertTrue(all(p.text.endswith(".") for p in result))

    def test_repeated_decoding_loop_is_capped(self):
        segments = [Segment(i, i + 1, "Gracias.") for i in range(6)] + [Segment(6, 7, "Fin.")]
        self.assertEqual(group_paragraphs(segments)[0].text, "Gracias. Gracias. Fin.")

    def test_two_legitimate_repeats_are_kept(self):
        result = group_paragraphs([Segment(0, 1, "Sí."), Segment(1, 2, "Sí.")])
        self.assertEqual(result[0].text, "Sí. Sí.")


class DiarizationSmoothingTests(unittest.TestCase):
    def words(self, spec):
        return [(a, b, " " + w) for a, b, w in spec]

    def test_isolated_word_between_same_speaker_is_absorbed(self):
        words = self.words([(0, 1, "uno"), (1, 1.3, "dos"), (1.3, 2.5, "tres")])
        result = label_segments(
            [Segment(0, 2.5, "uno dos tres", words=words)],
            [(0, 1.0, 1), (1.0, 1.3, 2), (1.3, 2.5, 1)],
        )
        self.assertEqual([(s.speaker, s.text) for s in result], [("Speaker 1", "uno dos tres")])

    def test_word_straddling_a_change_joins_nearest_side(self):
        words = self.words([(0, 2, "a"), (2, 2.3, "b"), (2.3, 4.5, "c")])
        result = label_segments(
            [Segment(0, 4.5, "a b c", words=words)], [(0, 2.0, 1), (2.0, 2.3, 1), (2.3, 4.5, 2)]
        )
        self.assertEqual(
            [(s.speaker, s.text) for s in result], [("Speaker 1", "a b"), ("Speaker 2", "c")]
        )

    def test_real_short_turn_far_from_neighbours_is_kept(self):
        words = self.words([(0, 3, "a"), (5, 5.3, "sí"), (8, 11, "b")])
        result = label_segments(
            [Segment(0, 11, "a sí b", words=words)], [(0, 3, 1), (5, 5.3, 2), (8, 11, 1)]
        )
        self.assertEqual([s.speaker for s in result], ["Speaker 1", "Speaker 2", "Speaker 1"])

    def test_word_in_a_gap_takes_nearest_turn(self):
        result = label_segments([Segment(3.2, 3.5, "hola")], [(0, 3, 1), (6, 9, 2)])
        self.assertEqual(result[0].speaker, "Speaker 1")


if __name__ == "__main__":
    unittest.main()
