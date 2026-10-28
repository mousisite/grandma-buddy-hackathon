// Grandma Buddy microphone recorder.
//
// Records her voice and turns it into the sound file Meta's speech-to-text
// needs: WAV, one channel (mono), 16,000 samples a second, 16-bit.
//
// How it works:
// 1. The browser's MediaRecorder records the microphone.
// 2. When she is done, the browser decodes the recording, and an
//    OfflineAudioContext resamples it to 16 kHz mono (the browser does the math).
// 3. encodeWav() writes the standard 44-byte WAV header and the samples.

"use strict";

var SAMPLE_RATE = 16000;
var recorder = null; // the MediaRecorder while recording
var chunks = []; // pieces of the recording as it comes in
var levelContext = null; // listens to the microphone for the voice ring
var analyser = null;
var levelSamples = null;

// Ask for the microphone and start recording. This fails (and the caller
// shows a kind message) if the microphone is blocked or missing.
function startRecording() {
  return navigator.mediaDevices
    .getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
    .then(function (stream) {
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (event) {
        chunks.push(event.data);
      };
      recorder.start();

      // A second, silent listener that only measures how loud she is.
      levelContext = new AudioContext();
      analyser = levelContext.createAnalyser();
      analyser.fftSize = 1024;
      levelSamples = new Float32Array(analyser.fftSize);
      levelContext.createMediaStreamSource(stream).connect(analyser);
    });
}

// How loud she is right now, from 0 (quiet) to 1 (loud).
// It measures the average size of the sound wave (its "RMS").
function voiceLevel() {
  if (!analyser) {
    return 0;
  }
  analyser.getFloatTimeDomainData(levelSamples);
  var sum = 0;
  for (var i = 0; i < levelSamples.length; i++) {
    sum += levelSamples[i] * levelSamples[i];
  }
  var rms = Math.sqrt(sum / levelSamples.length);
  return Math.min(1, rms * 6); // normal speech is about 0.02 to 0.15
}

// Stop recording, turn the microphone off, and give back the WAV file (a Blob).
function stopRecording() {
  return new Promise(function (resolve) {
    recorder.onstop = function () {
      resolve(new Blob(chunks, { type: recorder.mimeType }));
    };
    recorder.stop();
    // Release the microphone so the browser's "recording" dot goes away.
    recorder.stream.getTracks().forEach(function (track) {
      track.stop();
    });
    if (levelContext) {
      levelContext.close();
      levelContext = null;
      analyser = null;
    }
  })
    .then(function (blob) {
      return blob.arrayBuffer();
    })
    .then(toWav16k);
}

// Decode the recording and resample it to 16 kHz mono.
function toWav16k(recording) {
  var context = new AudioContext();
  return context
    .decodeAudioData(recording)
    .then(function (audio) {
      context.close();
      var offline = new OfflineAudioContext(1, Math.ceil(audio.duration * SAMPLE_RATE), SAMPLE_RATE);
      var source = offline.createBufferSource();
      source.buffer = audio;
      source.connect(offline.destination); // stereo is mixed down to mono here
      source.start();
      return offline.startRendering();
    })
    .then(function (rendered) {
      return encodeWav(rendered.getChannelData(0));
    });
}

// Write a standard WAV file: a 44-byte header, then each sample as a 16-bit number.
function encodeWav(samples) {
  var buffer = new ArrayBuffer(44 + samples.length * 2);
  var view = new DataView(buffer);

  function writeText(offset, text) {
    for (var i = 0; i < text.length; i++) {
      view.setUint8(offset + i, text.charCodeAt(i));
    }
  }

  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true); // file size after this point
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true); // size of the format section
  view.setUint16(20, 1, true); // 1 = plain PCM sound
  view.setUint16(22, 1, true); // 1 channel (mono)
  view.setUint32(24, SAMPLE_RATE, true); // samples per second
  view.setUint32(28, SAMPLE_RATE * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per sample
  view.setUint16(34, 16, true); // bits per sample
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true); // size of the sound data

  for (var i = 0; i < samples.length; i++) {
    // Samples go from -1 to 1. Scale them to whole numbers from -32768 to 32767.
    var sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}
