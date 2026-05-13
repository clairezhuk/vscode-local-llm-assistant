import os

def move_to_backup(folder, filename):
    path = folder + "/" + "backup" + "/" + filename
    return path