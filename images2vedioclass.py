from multiprocessing import Pool
import asyncio
import re
import edge_tts
import os
import random
import subprocess
import time

class VideoProcessing:
    def __init__(self,text:str,table,image_num):
        self.text = text
        self.table = table
        #[1, 1, 1, 3, 1, 3, 1, 1, 1, 4, 1, 2, 4, 3, 3, 3, 3, 4, 4, 2, 4, 3, 2, 3, 3, 3, 1, 1, 1, 3, 4, 3, 2, 3, 2, 1, 4, 3, 4, 3, 4, 2]
        self.images_num = image_num
        self.OVERWRITE="-y"
        self.INPUT_PATTERN = "./rebirth/image{}.png"
        self.OUTPUT_PREFIX = "vedio"
        self.MAX_JOBS = 6
        self.VOICE = "zh-CN-YunxiNeural"
        self.hardwareacc=" "
        self.XFADE_EFFECTS = [
            'fade', 'fadeblack', 'fadewhite', 'distance',
            'wipeleft', 'wiperight', 'wipeup', 'wipedown',
            'slideleft', 'slideright', 'slideup', 'slidedown',
            'smoothleft', 'smoothright', 'smoothup', 'smoothdown',
            'rectcrop', 'circlecrop', 'circleclose', 'circleopen',
            'horzclose', 'horzopen', 'vertclose', 'vertopen',
            'diagbl', 'diagbr', 'diagtl', 'diagtr',
            'hlslice', 'hrslice', 'vuslice', 'vdslice',
            'pixelize', 'radial', 'hblur',
            'wipetl', 'wipetr', 'wipebl', 'wipebr',
        ]
        self.ZOOMEFFECTS = [
            "z='min(zoom+0.0015,1.5)':x='if(gte(zoom,1.5),x,x+2)':y='if(gte(zoom,1.5),y,y+2)'",
            "z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/1.5)':y='ih/2-(ih/zoom/1.5)'",
        ]
        self.AUDIO_OUTPUT_FILE = "audio.mp3"
        self.SUBTITLE_VTT = "subtitle.vtt"
        self.PUNCTUATION=['，','。','！','？','；','：','\n','“','”',',']
        self.text=self.text.replace('\t','')
        # print(self.text)
        self.text_list=self.clause()

    def clause(self)->list[str]:
        start=0
        i=0
        text_list=[]
        while(i<len(self.text)):
            if self.text[i] in self.PUNCTUATION:
                try:
                    while self.text[i] in self.PUNCTUATION:
                        i+=1
                except:
                    pass
                text_list.append(self.text[start:i])
                start=i
            i+=1
        return text_list

    def generate_cn_subs(self,submaker:edge_tts.SubMaker) -> str:
        from edge_tts.submaker import formatter
        if len(submaker.subs) != len(submaker.offset):
            raise ValueError("subs and offset are not of the same length")
        data = "WEBVTT\r\n\r\n"
        j = 0
        for text in self.text_list:
            try:
                start_time = submaker.offset[j][0]
            except IndexError:
                return data
            try:
                while (submaker.subs[j + 1] in text):
                    j += 1
            except IndexError:
                pass
            data += formatter(start_time, submaker.offset[j][1], text)
            j += 1
        return data

    async def tts(self) -> None:
        communicate = edge_tts.Communicate(self.text, self.VOICE,rate="+50%")
        submaker = edge_tts.SubMaker()
        with open(self.AUDIO_OUTPUT_FILE, "wb") as file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])

        with open(self.SUBTITLE_VTT, "w", encoding="utf-8") as file:
                file.write(self.generate_cn_subs(submaker))

    def webvtt_to_srt(self, webvtt_content):
        pattern = r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\n(.+?)\n\n'
        matches = re.findall(pattern, webvtt_content)

        srt_content = ""
        for idx, (start, end, text) in enumerate(matches, start=1):
            srt_content += f"{idx}\n{start.replace('.', ',')} --> {end.replace('.', ',')}\n{text}\n\n"

        return srt_content

    def parse_subtitles(self, subtitle_file):
        time_pattern = re.compile(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})')

        subtitles = []
        prev_end_time = 0
        with open(subtitle_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            num_lines = len(lines)
            i = 0

            while i < num_lines:
                if not lines[i].strip():
                    i += 1
                    continue

                time_match = time_pattern.search(lines[i])
                if time_match:
                    start_hour, start_minute, start_second, start_millisecond = map(int, time_match.group(1, 2, 3, 4))
                    end_hour, end_minute, end_second, end_millisecond = map(int, time_match.group(5, 6, 7, 8))

                    start_time_ms = (start_hour * 3600000) + (start_minute * 60000) + (
                            start_second * 1000) + start_millisecond
                    end_time_ms = (end_hour * 3600000) + (end_minute * 60000) + (end_second * 1000) + end_millisecond

                    duration_ms = end_time_ms - prev_end_time

                    prev_end_time = end_time_ms

                    subtitle_text = ''
                    i += 1
                    while i < num_lines and lines[i].strip():
                        subtitle_text += lines[i]
                        i += 1

                    subtitles.append({
                        'start_time': start_time_ms,
                        'end_time': end_time_ms,
                        'duration': duration_ms,
                        'text': subtitle_text.strip()
                    })

                else:
                    i += 1

        return subtitles

    def sum_durations_according_to_list(self, input_file, output_file, num_list):
        def read_numbers_from_file(file_path):
            with open(file_path, 'r') as file:
                numbers = [float(line.strip()) for line in file]
            return numbers

        def write_numbers_to_file(file_path, numbers):
            with open(file_path, 'w') as file:
                for num in numbers:
                    file.write(f"{num:.3f}\n")

        numbers = read_numbers_from_file(input_file)
        result = []
        j = 0
        for i in num_list:
            result.append(sum(numbers[j:j + i]))
            j += i

        write_numbers_to_file(output_file, result)

    def get_video_information(self, input_file):
        cmd = f"ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 {input_file}"
        result = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        width, height = map(int, result.split("x"))
        return width, height

    def transition(self, i):
        input_file = self.INPUT_PATTERN.format(i)

        # input_width, input_height = self.get_video_information(input_file)

        output_file = f"{self.OUTPUT_PREFIX}_{i}.mp4"

        duration = self.durations[i - 1]

        if i == 1:
            ffmpeg_cmd = (
                f"ffmpeg {self.hardwareacc} {self.OVERWRITE} -loop 1 -r 30 -t {duration / 5:.3f} -i {input_file} "
                # f"-vf \"fade=in:st=0:d={duration / 4:.3f},scale={input_width}:{input_height}:force_original_aspect_ratio=decrease,pad={input_width}:{input_height}:(ow-iw)/2:(oh-ih)/2\" "
                f"-vf \"fade=in:st=0:d={duration / 4:.3f},scale=1920:1080\" "
                f"-c:v libx264 -r 30 -pix_fmt yuv444p effect_{output_file}"
            )
        else:
            ffmpeg_cmd = (
                f"ffmpeg {self.hardwareacc} {self.OVERWRITE} -loop 1 -i {self.INPUT_PATTERN.format(i - 1)} "
                f"-loop 1 -t {duration / 4:.3f} -i {input_file}\t"
                f"-filter_complex \"[0]scale=1920:1080[video0],"
                f"[video0][1]xfade=transition={random.choice(self.XFADE_EFFECTS)}:duration={duration / 5:.3f}:offset=0,format=yuv444p\" "
                f"-c:v libx264 -r 30 -pix_fmt yuv444p effect_{output_file}"
            )
        try:
            subprocess.run(ffmpeg_cmd, shell=True)
        except:
            pass

    def zoom_in(self, i):
        input_file = self.INPUT_PATTERN.format(i)
        input_width, input_height = self.get_video_information(input_file)

        output_file = f"{self.OUTPUT_PREFIX}_{i}.mp4"

        duration = self.durations[i - 1]
        ffmpeg_cmd = (
            f"ffmpeg {self.hardwareacc} {self.OVERWRITE} -i {input_file} -filter_complex \"zoompan={random.choice(self.ZOOMEFFECTS)}:d={int(duration * 3 * 25 / 4)}:s={input_width}x{input_height}\" -c:v libx264 -r 30 -pix_fmt yuv444p re_{output_file} "
        )
        try:
            subprocess.run(ffmpeg_cmd, shell=True)
        except:
            pass

    def merge_transition_zoom_in(self, i):
        output_file = f"{self.OUTPUT_PREFIX}_{i}.mp4"

        ffmpeg_cmd = (
            f"ffmpeg {self.hardwareacc} {self.OVERWRITE} -i effect_{output_file} -i re_{output_file} -filter_complex \"[0:v][1:v]concat=n=2:v=1[vv]\" -map \"[vv]\" {output_file}"
        )
        try:
            subprocess.run(ffmpeg_cmd, shell=True)
        except:
            pass

    def allprocess(self):
        random.seed(time.time())
        try:
            asyncio.run(self.tts())
        except:
            time.sleep(1)
            asyncio.run(self.tts())

        with open('subtitle.vtt', 'r', encoding='utf-8') as file:
            webvtt_content = file.read()

        srt_content = self.webvtt_to_srt(webvtt_content)

        with open('subtitle.srt', 'w', encoding='utf-8') as file:
            file.write(srt_content)

        subtitle_file = "subtitle.srt"
        subtitles = self.parse_subtitles(subtitle_file)

        with open("subtitle_time.txt", "w", encoding="utf-8") as f:
            for subtitle in subtitles:
                f.write(f"{subtitle['duration'] / 1000}\n")

        self.sum_durations_according_to_list('subtitle_time.txt', 'duration.txt', self.table)

        with open("duration.txt", "r") as duration_file:
            self.durations = [float(line.strip()) for line in duration_file]

        os.makedirs(os.path.dirname("./temp.txt"), exist_ok=True)
        with open("temp.txt", "w") as temp_list_file:
            for i in range(1, self.images_num + 1):
                output_file = f"{self.OUTPUT_PREFIX}_{i}.mp4"
                temp_list_file.write(f"file '{output_file}'\n")

        task_list = list(range(1, self.images_num + 1))
        # with Pool(self.MAX_JOBS) as pool:
        #     pool.map(self.transition, task_list)
        #     pool.close()
        #     pool.join()
        

        # with Pool(self.MAX_JOBS) as pool:
        #     pool.map(self.zoom_in, task_list)
        #     pool.close()
        #     pool.join()


        # with Pool(self.MAX_JOBS) as pool:
        #     pool.map(self.merge_transition_zoom_in, task_list)
        #     pool.close()
        #     pool.join()
        for i in task_list:
            self.transition(i)
        for i in task_list:
            self.zoom_in(i)
        for i in task_list:
            self.merge_transition_zoom_in(i)

        ffmpeg_cmd = (
            f"ffmpeg {self.hardwareacc} -y -f concat -i temp.txt "
            f"-vf \"scale=1920:1080\" "
            f"-c:v libx264 -r 30 -pix_fmt yuv444p just_vedio_{self.OUTPUT_PREFIX}.mp4"
        )
        subprocess.run(ffmpeg_cmd, shell=True)

        os.remove("temp.txt")

        for i in range(1, self.images_num + 1):
            output_file = f"{self.OUTPUT_PREFIX}_{i}.mp4"
            os.remove(output_file)
            os.remove(f"effect_{output_file}")
            os.remove(f"re_{output_file}")
            
        
        ffmpeg_cmd = (
            f"ffmpeg {self.hardwareacc} -y -i just_vedio_{self.OUTPUT_PREFIX}.mp4 -i audio.mp3 -vf \"subtitles=subtitle.srt\" "
            f"-c:s srt {self.OUTPUT_PREFIX}.mp4"
        )
        subprocess.run(ffmpeg_cmd, shell=True)
        os.remove(f"just_vedio_{self.OUTPUT_PREFIX}.mp4")


if __name__ == "__main__":
    video_processing = VideoProcessing(
        "你穿越大明成为第一贪官,入股赌坊兴办青楼,是沛县最大的保护伞,你更是当众受贿,万两白银,打点官职,就连沈安的县衙前院你都毫无避讳地摆满了金尊琉璃,可百姓非但不骂你,还纷纷求你多贪点,你本想就这样做个贪官逍遥一生,没想到朱元璋为追封祖地,乔装来到了你的属地,他一下就被你属地的沥青马路给震惊,黑面的马路不仅笔直平整,还有特殊规定,马车走在中间,行人只能走两边,这让朱元璋他们的马车畅通无阻,他又发现这周围两边行走的百姓一个个脸上洋溢着笑容,仿佛不为生活而发愁,朱元璋微微触动,这样的一幕,若是发生在盛唐,富宋倒也没什么,可如今是明朝初期,长期无休止的战争,消耗了大量人力财力,更有战争爆发频繁的地区,土地荒废,十里不见人烟。朱元璋想到之前的一幕幕,心中觉得太不可思议。马车继续往前行驶,来到了县门口,一位捕快伸出一只手,示意他们停车。这整个商队都是你的？闻言,朱元璋微微一愣,立即懂得对方的个话里的意思,不就是看他们都是外地商人,想要趁机捞上一笔。朱元璋的脸色一沉,但也没有多说什么,一个眼神过去,旁边的侍卫就掏出了一盒银子,捕快却一脸义正言辞地说,这是干什么的？他就是关心的问候一下吗？塞给自己钱干嘛？你们不收这个吗？朱元璋脸色好看了一些,但还是有些疑惑,捕快说到：我是看你们身家富有,所以想给你们提点建议,看到没进县门之后,沿着东边直走那条街上都是高档客栈,专门给你们这种有钱人住。朱元璋有些愣住,见他似乎有兴趣,捕快接着给他说了起来。是啊,来咱们沛县,你还不得先知道这里的场所划分吗。东边管住宿,南边管吃喝玩乐,西边是购物集市,找官府的话就去北面,想投资做生意,就去那边找咱们的县太爷,有点意思。朱元璋捋了捋胡,城卫捕快给介绍当地环境的,以前哪次不是塞银子,一行人穿过县门进入沛县,可没走几步路,便不由瞪大大眼睛,充满烟火气息的大街上,每一个人脸上都洋溢着其他地方看不到的笑容。朱元璋一行人走在大街上,有种恍若隔世的感觉,街上上开着各种的铺子,这里的行各业都有连青楼赌坊的旗子,也高高挂起.“一个小县,竟然如此繁华！”朱元璋微微沉思无比触动,马皇后露出亲和的笑容,微微点点头,很快,他们就来到了东区,朱元璋又是大开眼界,入眼望去,这里的房子竟然跟他们见到的寻常房子完全不同,这些房子竟然修得一栋一栋的,一排排过去,矗立了一大片,而且每一栋都修了四五层。朱彪和朱爽二人脸色也极为惊讶,虽然比不上金砖银瓦的皇宫,风格却见所未见。当朱元璋入住后,走到阳台上,看见沛县的全貌,几个区域也尽在他的眼下,他不禁感慨道“沛县治理的如此之好,这孟胤必是能臣。”",
        [1,1,1,3,1,3,1,1,1,4,1,2,4,3,3,3,3,4,4,2,4,3,2,3,3,3,1,1,1,3,4,3,2,3,2,1,4,3,4,3,4,2],
        42
    )
    video_processing.allprocess()
