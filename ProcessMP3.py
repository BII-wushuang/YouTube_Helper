from glob import glob
import subprocess
import os
from shutil import move

def processmp3(path='./*.mp3'):
    mp3list = glob(path)
    for file in mp3list:
        directory, filename = os.path.split(file)

        command = f'ffmpeg -i "{filename}" -acodec copy temp.mp3'
        subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        os.remove(filename)
        move('temp.mp3', filename)


if __name__ == '__main__':
    processmp3()