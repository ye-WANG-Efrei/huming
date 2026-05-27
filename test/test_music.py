import unittest
from music import search_song, get_lyric

class TestMusic(unittest.TestCase):

    def test_search_song(self):
        result = search_song("waiya")
        self.assertEqual(result["name"], "七溜八溜 WAIYA")
        self.assertEqual(result["artist"], "万妮达Vinida Weng")
        self.assertIsNotNone(result["original_id"])
        self.assertIsNotNone(result["encrypted_id"])
        self.assertGreater(result["duration"], 0)

    def test_get_lyric(self):
        song = search_song("waiya")
        lyrics = get_lyric(song["encrypted_id"], song["name"])
        self.assertGreater(len(lyrics), 0)
        self.assertIn("time", lyrics[0])
        self.assertIn("text", lyrics[0])

if __name__ == "__main__":
    unittest.main()