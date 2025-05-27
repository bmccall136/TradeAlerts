import matplotlib.pyplot as plt
import numpy as np
import os
from pathlib import Path

def generate_sparkline(data_points, filename, dark_mode=True):
    plt.figure(figsize=(2.5, 0.6), dpi=100)
    ax = plt.axes()
    bg_color = 'black' if dark_mode else 'white'
    fg_color = 'lime' if dark_mode else 'blue'
    ax.set_facecolor(bg_color)
    plt.plot(data_points, color=fg_color, linewidth=1.25)
    plt.axis('off')
    plt.tight_layout(pad=0)
    Path(os.path.dirname(filename)).mkdir(parents=True, exist_ok=True)
    plt.savefig(filename, bbox_inches='tight', pad_inches=0, transparent=False)
    plt.close()