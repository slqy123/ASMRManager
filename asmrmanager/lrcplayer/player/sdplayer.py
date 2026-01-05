import threading
import time
from typing import List

try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    raise ImportError(
        "sounddevice or soundfile is not installed, "
        "please install asmrmanager with player dependency."
    )

from .base import BasePlayer, Music


class SoundDevicePlayer(BasePlayer):
    def __init__(self, music_list: List[Music]) -> None:
        super().__init__(music_list)
        self.stream = None
        self.audio_data = np.zeros((0, 2), dtype=np.float32)
        self.samplerate = None
        self.current_frame = 0
        self.total_frames = 0
        self._is_playing = False
        self._is_paused = False
        self.lock = threading.Lock()
        self.play_start_time = None
        self.pause_time = 0
        self.paused_duration = 0

    @property
    def is_playing(self) -> bool:
        with self.lock:
            return self._is_playing

    def _load_audio(self):
        """加载音频文件"""
        self.audio_data, self.samplerate = sf.read(str(self.current.path))
        self.total_frames = len(self.audio_data)
        # 如果是单声道，转换为立体声
        if len(self.audio_data.shape) == 1:
            self.audio_data = np.column_stack(
                (self.audio_data, self.audio_data)
            )

    def _audio_callback(self, outdata, frames, time_info, status):
        """音频流回调函数"""
        if status:
            print(f"Status: {status}")

        with self.lock:
            if self._is_paused or not self._is_playing:
                outdata[:] = 0
                return

            remaining_frames = self.total_frames - self.current_frame

            if remaining_frames <= 0:
                outdata[:] = 0
                self._is_playing = False
                raise sd.CallbackStop()

            frames_to_play = min(frames, remaining_frames)

            outdata[:frames_to_play] = self.audio_data[
                self.current_frame : self.current_frame + frames_to_play
            ]

            if frames_to_play < frames:
                outdata[frames_to_play:] = 0

            self.current_frame += frames_to_play

    def play(self):
        """开始播放"""
        self.stop()
        self._load_audio()
        self.current_frame = 0
        with self.lock:
            self._is_playing = True
            self._is_paused = False
            self.play_start_time = time.time()
            self.paused_duration = 0

        # 创建音频流
        self.stream = sd.OutputStream(
            samplerate=self.samplerate,
            channels=2,
            callback=self._audio_callback,
            finished_callback=self._on_playback_finished,
        )
        self.stream.start()

    def _on_playback_finished(self):
        """播放结束回调"""
        with self.lock:
            self._is_playing = False

    def stop(self):
        """停止播放"""
        with self.lock:
            self._is_playing = False
            self._is_paused = False

        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self.current_frame = 0
        self.play_start_time = None
        self.paused_duration = 0

    @property
    def pos(self) -> int:
        """获取当前播放位置（毫秒）"""
        with self.lock:
            if self.samplerate is None:
                return 0
            return int((self.current_frame / self.samplerate) * 1000)

    @pos.setter
    def pos(self, pos: int):
        """设置播放位置（毫秒）"""
        pos = max(pos, 0)

        with self.lock:
            if self.samplerate is None:
                return

            # 将毫秒转换为帧数
            new_frame = int((pos / 1000) * self.samplerate)
            new_frame = min(new_frame, self.total_frames)

            self.current_frame = new_frame

            # 更新时间追踪
            if self._is_playing and not self._is_paused:
                self.play_start_time = time.time()
                self.paused_duration = 0

    def pause(self):
        """暂停播放"""
        with self.lock:
            if self._is_playing and not self._is_paused:
                self._is_paused = True
                self.pause_time = time.time()

    def unpause(self):
        """继续播放"""
        with self.lock:
            if self._is_playing and self._is_paused:
                self._is_paused = False
                if self.pause_time:
                    self.paused_duration += time.time() - self.pause_time
                    self.pause_time = 0

    @property
    def is_paused(self) -> bool:
        """是否处于暂停状态"""
        with self.lock:
            return self._is_paused

    def switch_music(self, index: int) -> None:
        """切换音乐"""
        self._index = index
        self.play()
