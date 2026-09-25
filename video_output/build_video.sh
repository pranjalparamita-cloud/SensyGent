#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
FF=./bin/ffmpeg
if [ ! -x "$FF" ]; then FF=$(command -v ffmpeg || true); fi
if [ -z "${FF:-}" ] || [ ! -x "$FF" ]; then
  echo "ffmpeg not found. Install ffmpeg or place it at ./bin/ffmpeg" >&2
  exit 1
fi

echo "== 1. Stitching Hindi narration with breathing pauses =="
$FF -y -loglevel error \
  -i audio/part1.mp3 -i audio/part2.mp3 -i audio/part3.mp3 \
  -f lavfi -t 0.5 -i anullsrc=r=44100:cl=stereo \
  -f lavfi -t 0.6 -i anullsrc=r=44100:cl=stereo \
  -f lavfi -t 2.0 -i anullsrc=r=44100:cl=stereo \
  -filter_complex "
    [0:a]aresample=44100,asetpts=PTS-STARTPTS[p1];
    [1:a]aresample=44100,asetpts=PTS-STARTPTS[p2];
    [2:a]aresample=44100,asetpts=PTS-STARTPTS[p3];
    [4:a]asplit=2[g1][g2];
    [3:a][p1][g1][p2][g2][p3][5:a]concat=n=7:v=0:a=1[out]" \
  -map "[out]" -c:a libmp3lame -b:a 192k audio/narration.mp3

ADUR=$($FF -i audio/narration.mp3 2>&1 | grep -m1 Duration | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+' | head -1 || true)
echo "narration duration: $ADUR"
ASEC=$(python3 - "$ADUR" <<'EOF'
import sys
h,m,s = sys.argv[1].split(':')
print(float(h)*3600+float(m)*60+float(s))
EOF
)
echo "narration seconds: $ASEC"
# Video timeline must be >= audio
MAXV=69.2667
if python3 -c "import sys; sys.exit(0 if $ASEC <= $MAXV else 1)"; then
  echo "audio fits timeline"
else
  echo "audio too long -> trimming to $MAXV"
  $FF -y -loglevel error -i audio/narration.mp3 -t $MAXV -c:a libmp3lame -b:a 192k audio/narration_tmp.mp3
  mv audio/narration_tmp.mp3 audio/narration.mp3
fi

echo "== 2. Rendering final video: 8 scenes, camera moves, crossfades, narration =="
# 8 scenes x 286 frames @30fps = 76.2667s raw; 7 x 1s crossfades => 69.2667s final
# xfade offsets: k * (286/30 - 1), k=1..7
$FF -y -loglevel error -stats \
  -i scenes/scene01.jpg -i scenes/scene02.jpg -i scenes/scene03.jpg -i scenes/scene04.jpg \
  -i scenes/scene05.jpg -i scenes/scene06.jpg -i scenes/scene07.jpg -i scenes/scene08.jpg \
  -i audio/narration.mp3 \
  -filter_complex "
    [0:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v0];
    [1:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='if(lte(on,1),1.15,max(zoom-0.0005,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v1];
    [2:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v2];
    [3:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='if(lte(on,1),1.15,max(zoom-0.0005,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v3];
    [4:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v4];
    [5:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='if(lte(on,1),1.15,max(zoom-0.0005,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v5];
    [6:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v6];
    [7:v]scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='if(lte(on,1),1.15,max(zoom-0.0005,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=286:s=1920x1080:fps=30,format=yuv420p[v7];
    [v0][v1]xfade=transition=fade:duration=1:offset=8.533333[x1];
    [x1][v2]xfade=transition=fade:duration=1:offset=17.066667[x2];
    [x2][v3]xfade=transition=fade:duration=1:offset=25.600000[x3];
    [x3][v4]xfade=transition=fade:duration=1:offset=34.133333[x4];
    [x4][v5]xfade=transition=fade:duration=1:offset=42.666667[x5];
    [x5][v6]xfade=transition=fade:duration=1:offset=51.200000[x6];
    [x6][v7]xfade=transition=fade:duration=1:offset=59.733333,fade=t=in:st=0:d=0.8,fade=t=out:st=68.1:d=0.9,format=yuv420p[vout];
    [8:a]aresample=44100[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart \
  "The_Lost_Star_Hindi_Cartoon.mp4"

echo "== 3. Done =="
ls -lh The_Lost_Star_Hindi_Cartoon.mp4
$FF -i The_Lost_Star_Hindi_Cartoon.mp4 2>&1 | grep -E "Duration|Stream" || true
