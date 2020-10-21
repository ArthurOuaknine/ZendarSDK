import sys
from os.path import join, exists
from contextlib import ExitStack
import argparse
import numpy as np
from collections import namedtuple
from matplotlib import pyplot as plt
import cv2

import data_pb2
from radar_image import RadarImage
from radar_point_cloud import RadarPointCloud
from radar_data_streamer import RadarDataStreamer
from radar_image_stream_display import RadarImageStreamDisplay
from radar_image_overlay import (
    draw_timestamp,
    draw_grid_line,
)
from video_writer import VideoWriter


IOPath = namedtuple('IOPath', ['image_pbs_path',
                               'pc_pbs_path',
                               'output_path'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i',
                        '--input-dir',
                        type=str,
                        help="dataset base directory",
                        required=True)
    parser.add_argument('-o',
                        '--output-dir',
                        type=str,
                        help="output video directory",
                        default=None)
    parser.add_argument('--radar-name',
                        action='append',
                        help="output video with specified radar serial number",
                        required=True)
    parser.add_argument('--frame-rate',
                        type=int,
                        help="output video frame rate",
                        default=10)
    parser.add_argument('--quality-factor',
                        type=int,
                        help="video compression quality factor",
                        default=23)
    parser.add_argument('--point-cloud',
                        default=False,
                        action='store_true',
                        help="create point cloud view instead")
    args = parser.parse_args()

    fig = plt.figure()
    fig.show()
    artist = None

    input_output_paths = []
    for radar_name in args.radar_name:
        output_path = None
        if args.output_dir is not None:
            output_path = join(args.output_dir, radar_name+".mp4")

        if args.point_cloud:
            io_path = IOPath(
                image_pbs_path = None,
                pc_pbs_path = join(args.input_dir, radar_name+"_points.pbs"),
                output_path = output_path)
        else:
            io_path = IOPath(
                image_pbs_path = join(args.input_dir, radar_name+"_images.pbs"),
                pc_pbs_path = None,
                output_path = output_path)

        input_output_paths.append(io_path)

    # create all videos
    for io_path in input_output_paths:
        video_writer = None
        data_streamer = None

        if io_path.image_pbs_path is not None:
            if not exists(io_path.image_pbs_path):
                sys.exit("%s does not exist" % io_path.image_pbs_path)

            data_streamer = convert_image_stream(io_path.image_pbs_path)

        else:
            if not exists(io_path.pc_pbs_path):
                sys.exit("%s does not exist" % io_path.pc_pbs_path)

            data_streamer = convert_point_cloud_stream(io_path.pc_pbs_path)

        for raw_data, im_rgb in data_streamer:
            (im_height, im_width, _) = im_rgb.shape
            im_rgb = overlay_metadata(raw_data, im_rgb)

            # setup onscreen display
            if artist is None:
                artist = fig.gca().imshow(
                    np.zeros(im_rgb.shape, dtype=np.uint8))

            # setup video writer
            if args.output_dir is not None and video_writer is None:
                video_writer = VideoWriter(io_path.output_path,
                                           im_width, im_height,
                                           args.frame_rate,
                                           args.quality_factor)

                video_writer = stack.enter_context(video_writer)

            # write out frame
            if video_writer is not None:
                video_writer(im_rgb)

            # on screen display
            artist.set_data(im_rgb)
            fig.canvas.draw()
            plt.pause(1e-4)


def convert_image_stream(image_pbs_path):
    """
    convert one radar image pbs file to RGB stream
    """
    radar_image_display = RadarImageStreamDisplay()

    with ExitStack() as stack:
        radar_data_streamer = stack.enter_context(
            RadarDataStreamer(image_pbs_path, data_pb2.Image, RadarImage))

        for radar_image in radar_data_streamer:
            im_rgb = radar_image_display(radar_image.image)

            yield radar_image, im_rgb


def convert_point_cloud_stream(pc_pbs_path):
    """
    convert one radar image pbs file to RGB stream
    """
    # default imaging area
    xmin = 0
    xmax = 60
    ymin = -30
    ymax = 30
    im_res = 0.1

    imsize_y = int((ymax - ymin) / im_res)
    imsize_x = int((xmax - xmin) / im_res)

    with ExitStack() as stack:
        point_cloud_streamer = stack.enter_context(
            RadarDataStreamer(pc_pbs_path, data_pb2.TrackerState, RadarPointCloud))

        for pc in point_cloud_streamer:
            pts = pc.point_cloud
            if len(pts) == 0:
                continue

            im_pts = np.array(pts)
            im_pts[:,0] = (im_pts[:,0] - xmin) / im_res
            im_pts[:,1] = (im_pts[:,1] - ymin) / im_res
            pc_image = np.zeros((imsize_y, imsize_x, 3), dtype=np.uint8)

            for (x, y, _) in im_pts:
                cv2.circle(pc_image,
                           center=(int(y), int(x)),
                           radius=1,
                           color=(255, 0, 0),
                           thickness=-1)

            yield pc, pc_image


def overlay_metadata(raw_image, im_rgb, show_range_marker=False):
    """
    # overlay range markers
    if show_range_marker:
        radar_position = radar_image.extrinsic.position
        center = radar_image.image_model.global_to_image(radar_position)
        pixels_per_meter = 1 / np.linalg.norm(radar_image.image_model.di)
        im_rgb = draw_grid_line(im_rgb,
                                center,
                                pixels_per_meter,
                                separation=5)
    """

    # overlay timestamp
    timestamp = "%2.2f" % raw_image.timestamp
    frame_id = "%d" % raw_image.frame_id
    im_rgb = draw_timestamp(im_rgb, frame_id + ":" + timestamp)

    return im_rgb


if __name__ == "__main__":
    main()
