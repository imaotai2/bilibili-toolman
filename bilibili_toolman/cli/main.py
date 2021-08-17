# region Setup
from ..bilisession import logger
from ..bilisession.common.submission import Submission
from ..providers import DownloadResult
from . import AttribuitedDict,setup_logging,prepare_temp,prase_args,sanitize_string,truncate_string,local_args as largs
import pickle,logging,sys,urllib.parse

TEMP_PATH = 'temp' # TODO : NOT chroot-ing for downloading into a different folder
sess = None

def download_sources(provider,arg) -> DownloadResult:
    resource = arg.resource
    opts = arg.opts
    try:
        opts = urllib.parse.parse_qs(opts,keep_blank_values=True)
        provider.update_config({k:v[-1] for k,v in opts.items()})
    except:opts = '无效选项'
    '''Passing options'''
    logger.info('下载源视频')
    logger.info('  - Type: %s - %s' % (provider.__name__,provider.__desc__))
    logger.info('  - URI : %s' % resource)    
    '''Downloading source'''
    try:
        return provider.download_video(resource)
    except Exception as e:
        logger.error('无法下载指定资源 - %s' % e)
        return        

def upload_sources(sources : DownloadResult,arg):
    '''To perform a indivudial task

    If multiple videos are given by the provider,the submission will be in multi-parts (P)
    Otherwise,only the given video is uploaded as a single part subject

    Args:

        provider - one of the modules of `providers`
        arg - task arguments dictionary    
            * resource - resoucre URI (must have)
            - opts     - options for uploader in query string e.g. format=best            
            - See `utils.local_args` for more arguments,along with thier details        
    '''    
    submission = Submission()    
    if not sources:return None,True
    logging.info('上传资源数：%s' % len(sources.results))    
    def sanitize(blocks,*a):
        do = lambda s : truncate_string(sanitize_string(s.format_map(blocks)),sess.MISC_MAX_DESCRIPTION_LENGTH)        
        return [do(i) for i in a]
    for source in sources.results:       
        '''If one or multipule sources'''        
        blocks = {'title':source.title,'desc':source.description,**source.extra} # for formatting
        title,description = sanitize(blocks,arg.title,arg.desc)
        logger.info('准备上传: %s' % title)
        '''Summary trimming'''
        try:
            endpoint, bid = sess.UploadVideo(source.video_path)
            cover_url = sess.UploadCover(source.cover_path)['data']['url'] if source.cover_path else ''
        except Exception as e:
            logger.critical('上传失败! - %s' % e)
            break
        if not endpoint:
            logger.critical('URI 获取失败!')
            break
        logger.info('资源已上传')
        with Submission() as video:
            '''Creatating a video per submission'''
            # A lot of these doesn't really matter as per-part videos only identifies themselves through UI via their titles
            video.cover_url = cover_url
            video.video_endpoint = endpoint
            video.biz_id = bid
            '''Sources identifiers'''   
            video.copyright = Submission.COPYRIGHT_REUPLOAD if not source.original else Submission.COPYRIGHT_SELF_MADE
            video.source = sources.soruce         
            video.thread = arg.thread_id
            video.tags = arg.tags.format_map(blocks).split(',')
            video.description = source.description # why tf do they start to use this again??
            video.title = title # This shows up as title per-part, invisible if video is single-part only
        '''Use the last given thread,tags,cover & description per multiple uploads'''                           
        submission.copyright = video.copyright or submission.copyright
        submission.thread = video.thread or submission.thread        
        submission.tags.extend(video.tags)
        submission.videos.append(video) # to the main submission
    '''Filling submission info'''        
    submission.source = sources.soruce
    submission.title = title # This shows up as the main title of the submission
    submission.description = description # This is the only description that gets shown
    '''Upload cover images for all our submissions as well'''
    cover_url = sess.UploadCover(sources.cover_path)['data']['url'] if sources.cover_path else ''
    submission.cover_url = cover_url
    '''Finally submitting the video'''
    submit_result=sess.SubmitSubmission(submission,seperate_parts=arg.seperate_parts)  
    dirty = False
    for result in submit_result['results']:
        if result['code'] == 0:logger.info('上传成功 - BVid: %s' % result['data']['bvid'])        
        else:
            logger.warning('上传失败: %s' % result['message'])        
            dirty = True
    return submit_result,dirty

global_args,local_args = None,None

def setup_session():
    '''Setup session with cookies in query strings & setup temp root'''
    global sess    
    if global_args.username and global_args.pwd:
        from ..bilisession.client import BiliSession
        sess = BiliSession() 
        sess.FORCE_HTTP = global_args.http           
        result = sess.LoginViaUsername(global_args.username,global_args.pwd)        
        logger.warning('MID:%s' % sess.mid)
        return result
    elif global_args.cookies:
        from ..bilisession.web import BiliSession
        sess = BiliSession()
        sess.FORCE_HTTP = global_args.http
        sess.LoginViaCookiesQueryString(global_args.cookies)
        self_ = sess.Self
        if not 'uname' in self_['data']:
            logger.error('Cookies无效: %s' % self_['message'])        
            return False
        logger.warning('ID:%s' % self_['data']['uname'])
        for arg in local_args.items():
            arg['seperate_parts'] = True
        logger.warning('Web端 API 无法进行多 P 上传！多P项目将被分为多个视频')  
        return True
    elif global_args.load:    
        unpickled = pickle.loads(open(global_args.load,'rb').read())
        sess = unpickled['session']
        sess.update(unpickled)
        sess.FORCE_HTTP = global_args.http
        logger.info('加载之前的登陆态')
        return True
    else:
        logger.error('缺失认证信息')
        return False

def __main__():
    global global_args,local_args
    setup_logging()
    global_args,local_args = prase_args(sys.argv)
    '''Parsing args'''
    if not setup_session():
        logging.fatal('登陆失败！')
        sys.exit(2)    
    else:         
        if global_args.http:
            logger.warning('强制使用 HTTP')
        logger.info('使用 %s API' % ('Web端' if sess.DEFAULT_UA else 'PC端'))        
        if global_args.save:
            logging.warning('保存登陆态到： %s' % global_args.save)
            open(global_args.save,'wb').write(pickle.dumps(sess.__dict__()))            
            sys.exit(0)
        prepare_temp(TEMP_PATH)
        # Output current settings        
        logging.info('任务总数: %s' % len(local_args.items()))        
        success,failure = [],[]
        fmt = lambda s: ('×','√')[s] if type(s) is bool else s
        for provider,arg_ in local_args.items():
            arg = AttribuitedDict(arg_)
            logger.info('任务信息：')
            for k,v in largs.items():
                logger.info('  - %s : %s' % (list(v.values())[0].split()[0],fmt(arg[k])))
            sources = download_sources(provider,arg)                   
            if arg.no_upload:
                logger.warn('已跳过上传')
            else:
                result,dirty = upload_sources(sources,arg)
                if not dirty:success.append((arg,result))
                else: failure.append((arg,None))
        if not failure:sys.exit(0)
        logging.warning('上传未完毕')
        sys.exit(1)