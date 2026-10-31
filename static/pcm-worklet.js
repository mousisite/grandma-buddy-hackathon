// Grandma Buddy: hands-free talking, the microphone's sound for Meta.
// An AudioWorklet runs beside the page and gets the microphone's sound in
// small pieces. listen.js runs the sound at 16 kHz already, so this only
// turns it into 16-bit numbers and hands the page 80 ms at a time (1280
// samples), which listen.js sends on to our server.

class BuddyMicrophone extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new Int16Array(1280);
    this.filled = 0;
  }

  process(inputs) {
    const sound = inputs[0] && inputs[0][0];
    if (sound) {
      for (let i = 0; i < sound.length; i++) {
        const sample = Math.max(-1, Math.min(1, sound[i]));
        this.frame[this.filled++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        if (this.filled === this.frame.length) {
          this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
          this.frame = new Int16Array(1280);
          this.filled = 0;
        }
      }
    }
    return true; // keep listening
  }
}

registerProcessor("buddy-microphone", BuddyMicrophone);
