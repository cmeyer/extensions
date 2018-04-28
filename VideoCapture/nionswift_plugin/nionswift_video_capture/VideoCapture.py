# standard libraries
import gettext
import logging
import threading
import time
import typing

# third party libraries
import numpy

# local libraries
from nion.ui import Declarative
from nion.utils import Model
from nion.utils import Registry


_ = gettext.gettext


# does not currently work. to switch to this, copy the hardware source code out of
# simulator mp and enable this. add necessary imports too.
def video_capture_process(buffer, cancel_event, ready_event, done_event):
    logging.debug("video capture process start")
    video_capture = cv2.VideoCapture(0)
    logging.debug("video capture: %s", video_capture)
    #video_capture.open(0)
    logging.debug("video capture open")
    while not cancel_event.is_set():
        retval, image = video_capture.read()
        logging.debug("video capture read %s", retval)
        if retval:
            logging.debug("video capture image %s", image.shape)
            with buffer.get_lock(): # synchronize access
                buffer_array = numpy.frombuffer(buffer.get_obj(), dtype=numpy.uint8) # no data copying
                buffer_array.reshape(image.shape)[:] = image
            ready_event.set()
            done_event.wait()
            done_event.clear()
        time.sleep(0.001)
    video_capture.release()

# informal measurements show read() takes approx 70ms (14fps)
# on Macbook Pro. CEM 2013-July.
# after further investigation, read() can take about 6ms on same
# computer. to do this, need to read out less frequently (by
# limiting frame rate to 15fps). this means that the next frame
# is constantly ready, so doesn't have to wait for it.
# the hardware manager will happily eat up 100% of python-cpu time.
MAX_FRAME_RATE = 20  # frames per second
MINIMUM_DUTY = 0.05  # seconds
TIMEOUT = 5.0  # seconds

def video_capture_thread(video_capture, buffer_ref, cancel_event, ready_event, done_event):

    while not cancel_event.is_set():
        start = time.time()
        retval, image = video_capture.read()
        if retval:
            buffer_ref[0] = numpy.copy(image)
            ready_event.set()
            done_event.wait()
            done_event.clear()
            elapsed = time.time() - start
            delay = max(1.0/MAX_FRAME_RATE - elapsed, MINIMUM_DUTY)
            cancel_event.wait(delay)
        else:
            buffer_ref[0] = None
            ready_event.set()

    video_capture.release()


class VideoCamera:

    def __init__(self, source):
        self.__source = source

    def update_settings(self, settings: dict) -> None:
        self.__source = settings.get("camera_index", settings.get("url"))

    def start_acquisition(self):
        video_capture = cv2.VideoCapture(self.__source)
        self.buffer_ref = [None]
        self.cancel_event = threading.Event()
        self.ready_event = threading.Event()
        self.done_event = threading.Event()
        self.thread = threading.Thread(target=video_capture_thread, args=(video_capture, self.buffer_ref, self.cancel_event, self.ready_event, self.done_event))
        self.thread.start()

    def acquire_data(self):
        self.ready_event.wait()
        self.ready_event.clear()
        data = self.buffer_ref[0].copy()
        self.done_event.set()
        return data

    def stop_acquisition(self):
        self.cancel_event.set()
        self.done_event.set()
        self.thread.join()


class VideoDeviceFactory:

    display_name = _("Video Capture")
    factory_id = "nionswift.video_capture"

    def make_video_device(self, settings: dict) -> typing.Optional[VideoCamera]:
        if settings.get("driver") == self.factory_id:
            source = settings.get("camera_index", settings.get("url"))
            video_device = VideoCamera(source)
            video_device.camera_id = settings.get("device_id")
            video_device.camera_name = settings.get("name")
            return video_device
        return None

    def describe_settings(self) -> typing.List[typing.Dict]:
        return [
            {'name': 'camera_index', 'type': 'int'},
            {'name': 'url', 'type': 'string'},
        ]

    def get_editor_description(self):
        u = Declarative.DeclarativeUI()

        url_field = u.create_line_edit(text="@binding(settings.url)", width=360)
        camera_index_combo = u.create_combo_box(items=["None", "0", "1", "2", "3"], current_index="@binding(camera_index_model.value)")

        label_column = u.create_column(u.create_label(text=_("URL:")), u.create_label(text=_("Camera Index (0 for none):")), spacing=4)
        field_column = u.create_column(url_field, camera_index_combo, spacing=4)

        return u.create_row(label_column, field_column, u.create_stretch(), spacing=12)

    def create_editor_handler(self, settings):

        class EditorHandler:

            def __init__(self, settings):
                self.settings = settings

                self.camera_index_model = Model.PropertyModel()

                def camera_index_changed(index):
                    formats = [None, 0, 1, 2, 3]
                    self.settings.camera_index = formats[index]

                self.camera_index_model.on_value_changed = camera_index_changed

                self.camera_index_model.value = self.settings.camera_index + 1 if self.settings.camera_index is not None else 0

        return EditorHandler(settings)




# see http://docs.opencv.org/index.html
# fail cleanly if not able to import
import_error = False
try:
    import cv2
except ImportError:
    import_error = True


class VideoCaptureExtension:

    # required for Swift to recognize this as an extension class.
    extension_id = "nion.swift.extensions.video_capture"

    def __init__(self, api_broker):
        # grab the api object.
        api = api_broker.get_api(version="1", ui_version="1")

        global import_error
        if import_error:
            api.raise_requirements_exception(_("Could not import cv2."))

    Registry.register_component(VideoDeviceFactory(), {"video_device_factory"})

    def close(self):
        pass
