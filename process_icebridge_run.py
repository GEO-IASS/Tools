#!/usr/bin/env python


# Process an entire run of icebrige images

import os, sys, optparse, datetime, multiprocessing, time

sys.path.insert(0, '/home/oalexan1/projects/StereoPipeline/src/asp/Python')
import asp_cmd_utils, asp_geo_utils



# This block of code is just to get a non-blocking keyboard check!
import signal
class AlarmException(Exception):
    pass
def alarmHandler(signum, frame):
    raise AlarmException
def nonBlockingRawInput(prompt='', timeout=20):
    signal.signal(signal.SIGALRM, alarmHandler)
    signal.alarm(timeout)
    try:
        text = raw_input(prompt)
        signal.alarm(0)
        return text
    except AlarmException:
        pass # Timeout
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    return ''
    

def processPair(imageA, imageB, cameraA, cameraB, lidarFolder,
                outputFolder, options):
    '''Processes a single image pair'''

    suppressOutput = False
    redo           = False

    # Just set the options and call the pair python tool.
    # We can try out bundle adjustment for intrinsic parameters here.
    # options = '' #'--bundle-adjust'
    cmd = ('python process_icebridge_pair.py --lidar-overlay --align-max-displacement 20 %s %s %s %s %s %s %s' 
           % (imageA, imageB, cameraA, cameraB, lidarFolder, outputFolder, options))
    print("---now here!!!")
    asp_cmd_utils.executeCommand(cmd, None, suppressOutput, redo)

def getFrameNumberFromFilename(f):
    '''Return the frame number of an image or camera file'''
    parts = os.path.basename(f).split('_')
    return int(parts[0])
    
def main(argsIn):

    try:
        usage = "usage: process_icebridge_run.py <image_folder> <camera_folder> <lidar_folder> <output_folder>[--help]\n  "
        parser = optparse.OptionParser(usage=usage)

        parser.add_option('--start-frame', dest='startFrame', default=-1,
                          type='int', help='The frame number to start processing with.')
        parser.add_option('--stop-frame', dest='stopFrame', default=-1,
                          type='int', help='The frame number to finish processing with.')        

        parser.add_option("--south", action="store_true", default=False, dest="isSouth",  
                          help="MUST be set if the images are in the southern hemisphere")

        parser.add_option("--shared-bundle", action="store_true", default=False, dest="sharedBundle",  
                          help="Bundle adjust all cameras at once.")

        parser.add_option('--num-processes', dest='numProcesses', default=1,
                          type='int', help='The number of simultaneous processes to run.')
                          
        parser.add_option("--nosgm", action="store_true", default=False, dest="nosgm",  
                          help="If not to use SGM")
        #parser.add_option("--lidar-overlay", action="store_true", default=False, dest="lidarOverlay",  
        #                  help="Generate a lidar overlay for debugging")

        #parser.add_option("--bundle_adjust", action="store_true", default=False, dest="bundleAdjust",  
        #                  help="Run bundle adjustment between the two images")

        #parser.add_option('--num-threads', dest='numThreads', default=None,
        #                  type='int', help='The number of threads to use for processing.')

        #parser.add_option('--dem-resolution', dest='demResolution', default=0.4,
        #                  type='float', help='Generate output DEMs at this resolution.')

        #parser.add_option('--align-max-displacement', dest='maxDisplacement', default=20,
        #                  type='float', help='Max displacement value passed to pc_align.')


        (options, args) = parser.parse_args(argsIn)

        if len(args) < 5:
            print usage
            return 0

        imageFolder  = args[1]
        cameraFolder = args[2]
        lidarFolder  = args[3]
        outputFolder = args[4]

    except optparse.OptionError, msg:
        raise Usage(msg)

    
    # Check the inputs
    for f in [imageFolder, cameraFolder, lidarFolder]:
        if not os.path.exists(f):
            print 'Input file '+ f +' does not exist!'
            return 0
    if not os.path.exists(outputFolder):
        os.mkdir(outputFolder)

    suppressOutput = False
    redo           = False

    print '\nStarting processing...'
    
    # Get a list of all the input files
    imageFiles  = os.listdir(imageFolder)
    cameraFiles = os.listdir(cameraFolder)
    # Filter the file types
    imageFiles  = [f for f in imageFiles  if (os.path.splitext(f)[1] == '.tif') and ('sub' not in f)] 
    cameraFiles = [f for f in cameraFiles if os.path.splitext(f)[1] == '.tsai']
    imageFiles.sort() # Put in order so the frames line up
    cameraFiles.sort()
    imageFiles  = [os.path.join(imageFolder, f) for f in imageFiles ] # Get full paths
    cameraFiles = [os.path.join(cameraFolder,f) for f in cameraFiles]

    numFiles = len(imageFiles)
    if (len(cameraFiles) != numFiles):
        print 'Error: Number of image files and number of camera files must match!'
        return -1
    
    # Check that the files are properly aligned
    imageString  = ''
    cameraString = ''
    for (image, camera) in zip(imageFiles, cameraFiles): 
        frameNumber = getFrameNumberFromFilename(image)
        if (getFrameNumberFromFilename(camera) != frameNumber):
          print 'Error: input files do not align!'
          print (image, camera)
          return -1
        imageString  += image +' ' # Build strings for the bundle_adjust step
        cameraString += camera+' '
        

    # TODO: Intrinsics???
    # Bundle adjust all of the cameras
    # - Could use an overlap of 4 but there is very little overlap at that point.
    # - If we start dealing with crossover paths we can use the KML overlap method.
    print 'Setting up bundle adjustment...'
    baFolder = os.path.join(outputFolder, 'group_bundle')
    baPrefix = os.path.join(baFolder,     'out')
    cmd = ('bundle_adjust '+ imageString + cameraString 
            + ' --overlap-limit 3 --local-pinhole --solve-intrinsics -o '+ baPrefix)
    suppressOutput = False
    redo           = False
    baOutFile = baPrefix +'-'+ os.path.basename(cameraFiles[-1])

    print("--cmd is ", cmd)
    print("--ba file ", baOutFile)
    
    asp_cmd_utils.executeCommand(cmd, baOutFile, suppressOutput, redo)
    
    print 'Bundle adjustment finished!'
    
    # Generate a map of initial camera positions
    orbitvizBefore = os.path.join(outputFolder, 'cameras_in.kml')
    orbitvizAfter  = os.path.join(outputFolder, 'cameras_post_ba.kml')
    vizString  = ''
    for (image, camera) in zip(imageFiles, cameraFiles): 
        vizString += image +' ' + camera+' '
    cmd = 'orbitviz --hide-labels -t nadirpinhole -r wgs84 -o '+ orbitvizBefore +' '+ vizString
    asp_cmd_utils.executeCommand(cmd, orbitvizBefore, suppressOutput, redo)

    # Update the list of camera files to the ba files
    baOutFiles  = os.listdir(baFolder)
    cameraFiles = [os.path.join(baFolder, f) for f in baOutFiles if '.tsai' in f]
    cameraFiles.sort()

    # Generate a map of post-bundle_adjust camera positions
    vizString  = ''
    for (image, camera) in zip(imageFiles, cameraFiles): 
        vizString += image +' ' + camera+' '
    cmd = 'orbitviz --hide-labels -t nadirpinhole -r wgs84 -o '+ orbitvizAfter +' '+ vizString
    asp_cmd_utils.executeCommand(cmd, orbitvizAfter, suppressOutput, redo)
    
    print 'Starting processing pool with ' + str(options.numProcesses) +' processes.'
    pool = multiprocessing.Pool(options.numProcesses)
    
    MAX_COUNT = 2 # DEBUG
    
    # Call process_icebridge_pair on each pair of images.
    taskHandles = []
    for i in range(0,numFiles-1):
    
        imageA  = imageFiles [i  ]
        imageB  = imageFiles [i+1]
        cameraA = cameraFiles[i  ]
        cameraB = cameraFiles[i+1]

        # Check if this is inside the user specified frame range
        frameNumber = getFrameNumberFromFilename(imageA)
        if options.startFrame and (frameNumber < options.startFrame):
            continue
        if options.stopFrame and (frameNumber > options.stopFrame):
            continue

        print 'Processing frame number: ' + str(frameNumber)
        
        # Check if the output file already exists.
        thisOutputFolder = os.path.join(outputFolder, str(frameNumber))
        thisDemFile      = os.path.join(thisOutputFolder, 'DEM.tif')
        if os.path.exists(thisDemFile):
          continue
          
        # Generate the command call
        extraOptions = ''
        if options.nosgm:
            extraOptions = '--nosgm'

        cmd = ('python process_icebridge_pair.py --lidar-overlay --align-max-displacement 20 %s %s %s %s %s %s %s' 
                   % (imageA, imageB, cameraA, cameraB, lidarFolder, thisOutputFolder, extraOptions))
        print("33---now here!!!")
        print("will run " + " ".join(cmd))
        
        taskHandles.append(pool.apply_async(processPair, 
            (imageA, imageB, cameraA, cameraB, lidarFolder, thisOutputFolder, extraOptions)))
            
        #if len(taskHandles) >= MAX_COUNT:
        #    break # DEBUG
            
    # End of loop through input file pairs
    notReady = len(taskHandles)
    print 'Finished adding ' + str(notReady) + ' tasks to the pool.'
    
    # Wait for all the tasks to complete
    while notReady > 0:
        # Wait and see if the user presses a key
        msg = 'Waiting on ' + str(notReady) + ' processes, press q<Enter> to abort...\n'
        keypress = nonBlockingRawInput(prompt=msg, timeout=20)
        if keypress == 'q':
            print 'Recieved quit command!'
            break
        # Otherwise count up the tasks we are still waiting on.
        notReady = 0
        for task in taskHandles:
            if not task.ready():
                notReady += 1
    
    # Either all the tasks are finished or the user requested a cancel.
    # Clean up the processing pool
    PROCESS_POOL_KILL_TIMEOUT = 3
    pool.close()
    time.sleep(PROCESS_POOL_KILL_TIMEOUT)
    pool.terminate()
    pool.join()
    
    # BUNDLE_ADJUST

    ## TODO: Solve for intrinsics?
    #bundlePrefix = os.path.join(outputFolder, 'bundle/out')
    #cmd = ('bundle_adjust %s %s %s %s -o %s %s -t nadirpinhole --local-pinhole' 
    #             % (imageA, imageB, cameraA, cameraB, bundlePrefix, threadText))
    ## Point to the new camera models
    #cameraA = bundlePrefix +'-'+ os.path.basename(cameraA)
    #cameraB = bundlePrefix +'-'+ os.path.basename(cameraB)
    #asp_cmd_utils.executeCommand(cmd, cameraA, suppressOutput, redo)




# Run main function if file used from shell
if __name__ == "__main__":
    sys.exit(main(sys.argv))



