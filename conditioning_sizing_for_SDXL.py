class sizing_node:
    ''' This node takes native resolution, aspect ratio, and original resolution. It uses these to 
        calculate and output the latent dimensions in an appropriate bucketed resolution with 64-multiples 
        for each side (which double as the target_height/_width), the resolution for the width and height
        conditioning inputs (representing a hypothetic "original" image in the training data), and the
        crop_w and crop_h conditioning inputs, which are determined by the difference between the model
        resolution and the upscaled/downscaled training image along that dimension (and divided by two).
        The downscale output can optionally be connected to an "upscale by" node to automatically downscale
        gens to match the "original size" set in this node. (Most don't like downscaling, this was for my 
        own use.) Set to 0.0 or just don't connect the output to anything if you don't want downscaling.

        crop_extra just adds a fraction of the image size to the crop inputs. Leave at 0.0 unless you want 
        to experiment with SDXL's ability to reproduce cropped images.

        The input fields accept different kinds of string inputs to produce different results. Here's a list:
        "native_res"
            - "1000x10" - returns 100, the square root of 10 * 1000 (as an int).
            - "100" - returns 100
            - "100.0" - returns 100
            (this should generally be left at 1024 for SDXL.)
        "aspect"
            these are all correct ways of getting a 1:2 aspect ratio:
            - "2:4"
            - "1x2"
            - "0.5"
            - "1 by 2"
        "original_res"
            - "600" - returns 600 on the long side, and the short side is calculated to match the aspect ratio.
            - "600x600" - returns 600 by 600, and crop_w and crop_h are calculated accordingly if this doesn't
                match the aspect ratio of the image resolution.
            - "2.0" - returns dimensions double those of the generation. So if you're generating at 1024x1024,
                this will return 2048x2048.
    '''

    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "native_res": ("STRING", {
                    "multiline": False,
                    "default": "1024"
                }),
                "aspect": ("STRING", {
                    "multiline": False,
                    "default": "1:1"
                }),
                "original_res": ("STRING", {
                    "multiline": False,
                    "default": "800x1200"
                }),
                "crop_extra": ("FLOAT", {
                    "default": 0.0,
                    "max": 1.0,
                    "min": 0.0,
                    "step": 0.001
                }),
                "downscale_effect": ("FLOAT", {
                    "default": 0.0,
                    "max": 1.0,
                    "min": 0.0,
                    "step": 0.001
                }),
                "verbose": (["disabled", "basic", "full"],),
                "fit_aspect_to_bucket": (["disabled", "enabled"],)
            }
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "INT", "INT", "FLOAT")   
    RETURN_NAMES = ("width", "height", "target_width", "target_height", "crop_w", "crop_h", "downscale")

    FUNCTION = "get_sizes"

    CATEGORY = "sizing"

    def parse_res(self, input_text):


        if "." in input_text:
            return float(input_text)

        


        striptext = "".join(i for i in input_text if i in set("1234567890xby*:-"))

        replace_list = ["by", "*", ":"]
        for i in replace_list:
            striptext = striptext.replace(i, "x")

        if "x" in striptext:
            w, h = striptext.split("x", 1)
            return (int(w), int(h))
        else:
            return int(striptext)

    def make_64(self, num):
        num = int(num)
        return num // 64 * 64 if num % 64 < 32 else (num + 1) // 64 * 64

    def find_fraction(self, decimal):
        ''' A bit silly/wasteful, but this is for describing aspect ratio to anons who put in a float value and
            want verbose reporting. It just iterates over all ints, starting at 1, until it finds one where 
            n / round(n/aspect) is close enough to the given decimal, and 'close enough' is defined according to
            how many decimal points you give it, to a maximum of 5. (Without a maximum this could get very slow.)

            Maybe this is adding some bloat but I think it's fun. It shouldn't get called if you don't choose to 
            turn on "verbose". The absolute worst case 
        '''
        decimal = round(decimal, 5)

        x = str(decimal)
        xf =len(x) - (x.find(".") + 1)
        tolerance = 10**(-xf-1)*5
        bounds = (decimal - tolerance, decimal + tolerance)

        i = 0
        past0 = False
        while past0 == False:
            i += 1
            if round(i/decimal) == 0.0:
                continue
            else:
                past0 = True
                t = i / round(i/decimal)
                if bounds[0] <= t < bounds[1]:
                    return (i, int(round(i/decimal)))

        while True:
            i+= 1
            t = i / round(i/decimal)
            if bounds[0] <= t < bounds[1]:
                return (i, int(round(i/decimal)))


    def get_sizes(self, native_res, aspect, original_res, crop_extra, downscale_effect, verbose, fit_aspect_to_bucket):

        # initialize the verbose variables for reporting
        v_aspect = None
        v_crops = None
        v_crops_extra = None
        v_postscale = None
        v_downscale = None
        v = verbose == "full"


        # turn these string inputs into tuples, ints, or floats
        native_res = self.parse_res(native_res)
        aspect = self.parse_res(aspect)
        original_res = self.parse_res(original_res)

        #initialize some vars
        width, height, target_width, target_height, crop_w, crop_h, downscale = None, None, None, None, None, None, None


        # parse the native_res input -> int
        if isinstance(native_res, tuple):
            native_res = int((native_res[0] * native_res[1])**(1/2))
        elif isinstance(native_res, float):
            native_res = int(native_res * 1024)


        # parse the aspect input -> float
        if isinstance(aspect, tuple):
            if v: v_aspect = aspect
            aspect = aspect[0]/aspect[1]
        elif v:
            v_aspect = self.find_fraction(aspect)


        # match the buckets
        c = (native_res**2 / aspect)**(1/2)
        target_width = self.make_64(c * aspect)
        target_height = self.make_64(c)

        if fit_aspect_to_bucket == "enabled":
            aspect = target_width/target_height   # adjust aspect to match these multiples of 64


        # parse the original resolution input -> width, height
        if isinstance(original_res, float):
            width, height = int(original_res * target_width), int(original_res * target_height)
        elif isinstance(original_res, tuple):
            width, height = original_res
        else:
            if target_width > target_height:
                width = original_res
                height = int(original_res / aspect)
            else:
                width = int(original_res * aspect)
                height = original_res


        if width/height == target_width/target_height:
            if v: v_crops, v_postscale = (0, 0), (target_width, target_height, target_width/width, True)
            crop_w = int(target_width*crop_extra)//2
            crop_h = int(target_height*crop_extra)//2
            downscale = (1-crop_extra) * width / target_width
        elif width/height > target_width/target_height:
            x0 = int(width * target_height/height)
            x1 = x0 - target_width
            if v: v_crops, v_postscale = (x1, 0), (x0, target_height, target_height/height, False)
            crop_w = int(x1 + target_width * crop_extra)//2
            crop_h = int(target_height*crop_extra)//2
            downscale = (1-crop_extra) * height / target_height
        else:
            x0 = int(height * target_width/width)
            x1 = x0 - target_height
            if v: v_crops, v_postscale = (0, x1), (target_width, x0, target_width/width, False)
            crop_w = int(target_width*crop_extra)//2
            crop_h = int(x1 + target_height * crop_extra)//2
            downscale = (1-crop_extra) * width/target_width


        if v: v_crops_extra = (int(target_width*(crop_extra))//2, int(target_height*(crop_extra))//2)

        if v: v_downscale = (downscale,)
        downscale = 1 - ((1 - downscale) * downscale_effect)
        if v: 
            v_downscale += (downscale,)

        if verbose == "basic":
            print(f'''width: {width}
height: {height}
crop_w: {crop_w}
crop_h: {crop_h}
target_width: {target_width}
target_height: {target_height}
downscale: {downscale}''')

        elif verbose == "full":

            # scaling to fit bucketing
            scaling_line = f"Original dimensions: {width}x{height}\n - scaled by factor of {v_postscale[2]} to {v_postscale[0]}x{v_postscale[1]}."




            # cropping data
            crop_line = ""
            if v_crops == (0, 0):
                crop_line = "No cropping required."
            else:
                crop_line = f'{max(*v_crops)//2} pixels cropped from {"left and right sides" if v_crops[0] > v_crops[1] else "top and bottom"} to fit.'
            if crop_extra > 0:
                crop_line += f'\n - additional {v_crops_extra[0]}, {v_crops_extra[1]} pixels removed from width, height.'

            downscale_line = ""
            #downscale
            if downscale_effect > 0:
                if downscale_effect == 1.0:
                    downscale_line = f"Scale resulting image by {v_downscale[1]}"
                else:
                    downscale_line = f"Scale resulting image by {v_downscale[1]} ({v_downscale[0]}, effect strength {int(100*round(downscale_effect, 2))}%)"
                downscale_line += f"\n Final image size: {int(downscale*target_width)}x{int(downscale*target_height)}"

            #print
            print(
f'''
---- Sizing Data (debug) 
 native resolution: {int(native_res)}
 aspect ratio: {v_aspect[0]}:{v_aspect[1]}
 Generation size of {target_width}x{target_height}
 {scaling_line}
 {crop_line}
 {downscale_line}

---- Output Values
 width: {width}
 height: {height}
 target_width: {target_width}
 target_height: {target_height}
 crop_w: {crop_w}
 crop_h: {crop_h}
 downscale: {downscale}

* disable verbose on the sizing node to hide this information.
'''
                )


        #fin
        return (width, height, target_width, target_height, crop_w, crop_h, downscale)



NODE_CLASS_MAPPINGS = {
    "sizing_node": sizing_node

}

NODE_DISPLAY_NAME_MAPPINGS = {
    "sizing_node": "get resolutions for generation"
}