"""Multimodal Perception and Decode & Infer — the producer side of the cycle.

Three adapters converge on one type. Text, speech and generated input all end in a
sentence, so the moment ASR returns a string they are indistinguishable and one decoder
serves all three; the genuine extra cost of speech is the ASR plumbing and microphone
gating, not a parallel processing path.

Everything here is a **producer**: it makes `Utterance`s and, once the decoder lands,
evidence. Nothing here reads the affect model, and nothing here holds the observer
registry — perception's `Utterance` is published by whatever drives an adapter, and the
evidence derived from it is published by the evidence loop on every producer's behalf.
"""
