'''bilibili-toolman 哔哩哔哩工具人'''
# region Setup
from re import sub
from bilisession import BiliSession,Submission
from providers import DownloadResult
from utils import setup_logging,prepare_temp,report_progress,save_cookies,load_cookies,prase_args,sanitize_string,truncate_string,local_args as largs
import logging,sys,time,urllib.parse

sess = BiliSession()

def perform_task(provider,args,report=report_progress):
    '''To perform a indivudial task

    If multiple videos are given by the provider,the submission will be in multi-parts (P)
    Otherwise,only the given video is uploaded as a single part subject

    Args:

        provider - one of the modules of `providers`
        args - task arguments dictionary    
            * resource - resoucre URI (must have)
            - opts     - options for uploader in query string e.g. format=best            
            - See `utils.local_args` for more arguments,along with thier details
        report : A function takes (current,max) to show progress of the upload
    '''
    logger = sess.logger
    resource = args['resource']    
    opts = args['opts']
    try:
        opts = urllib.parse.parse_qs(opts)
        provider.update_config({k:v[-1] for k,v in opts.items()})
    except:opts = 'INVALID OPTIONS'
    '''Passing options'''
    self_info = sess.Self
    if not 'uname' in self_info['data']:
        return logger.error(self_info['message'])        
    logger.warning('Uploading as %s' % self_info['data']['uname'])
    logger.info('Processing task:')
    logger.info('  - Type: %s - %s' % (provider.__name__,provider.__desc__))
    logger.info('  - URI : %s' % resource)
    for k,v in largs.items():logger.info('  - %s : %s' % (v[0],args[k]))
    logger.info('Fetching source video')
    '''Downloading source'''
    try:
        sources : DownloadResult = provider.download_video(resource)
    except Exception as e:
        logger.error('Cannot download specified resource - %s - skipping' % e)
        return 
    submission = Submission()
    logging.info('Processing total of %s sources' % len(sources.results))
    for source in sources.results:       
        '''If one or multipule sources'''        
        format_blocks = {
            'title':source.title,
            'desc':source.description,            
        }
        source.title = sanitize_string(truncate_string(args['title_fmt'] % format_blocks,80))
        source.description = sanitize_string(truncate_string(args['desc_fmt'] % format_blocks,2000))        
        logger.info('Uploading: %s' % source.title)
        '''Summary trimming'''      
        basename, size, endpoint, config, state , pic = [None] * 6
        while True:
            try:
                basename, size, endpoint, config, state = sess.UploadVideo(source.video_path,report=report)
                pic = sess.UploadCover(source.cover_path)['data']['url'] if source.cover_path else ''
                break
            except Exception:
                logger.warning('Failed to upload - skipping')                
                break
        if not endpoint:
            continue
        logger.info('Upload complete')
        # submit_result=sess.SubmitVideo(submission,endpoint,pic['data']['url'],config['biz_id'])
        with Submission() as video:
            video.cover_url = pic
            video.video_endpoint = endpoint
            video.biz_id = config['biz_id']
            '''Sources identifiers'''   
            video.copyright = Submission.COPYRIGHT_REUPLOAD if not source.original else Submission.COPYRIGHT_SELF_MADE
            video.source = sources.soruce         
            video.thread = args['thread_id']
            video.tags = args['tags'].split(',')
            video.description = source.description
            video.title = source.title            
        '''Use the last given thread,tags,cover & description per multiple uploads'''                           
        submission.thread = video.thread or submission.thread        
        submission.tags.extend(video.tags)
        submission.videos.append(video)
    '''Filling submission info'''
    submission.source = sources.soruce

    submission.title = sources.title
    submission.description = sources.description

    '''Make cover image for all our submissions as well'''
    pic = sess.UploadCover(sources.cover_path)['data']['url'] if sources.cover_path else ''
    submission.cover_url = pic
    '''Finally submitting the video'''
    submit_result=sess.SubmitVideo(submission,seperate_parts=args['is_seperate_parts'])  
    dirty = False
    for result in submit_result['results']:
        if result['code'] == 0:logger.info('Upload success - BVid: %s' % result['data']['bvid'])        
        else:
            logger.warning('Upload Failed: %s' % result['message'])        
            dirty = True
    return submit_result,dirty

def setup_session(cookies:str):
    '''Setup session with cookies in query strings & setup temp root'''
    return prepare_temp() and sess.load_cookies(cookies)

global_args,local_args = None,None

def __tasks__():
    logging.info('Total tasks: %s' % len(local_args))
    success,failure = [],[]

    for provider,args in local_args:
        result,dirty = perform_task(provider,args,report_progress if global_args['show_progress'] else lambda current,max:None )
        if not dirty:success.append((args,result))
        else: failure.append((args,None))
    if not failure:sys.exit(0)
    logging.warning('Dirty flag set,upload might be unfinished')
    sys.exit(1)

if __name__ == "__main__":
    setup_logging()
    global_args,local_args = prase_args(sys.argv)
    '''Parsing args'''
    save_cookies(global_args['cookies'])
    '''Saving / Loading cookies'''    
    if not setup_session(load_cookies()):
        logging.fatal('Unable to set working directory,quitting')
        sys.exit(2)    
    else:
        __tasks__()
    sys.exit(0)