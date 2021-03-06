'''
Injects errors of specific type into seed corpus.
Created on 9 Oct 2015

@author: Karin
'''
#! /usr/bin/python
#-*-coding:utf-8-*-
import argparse, logging, os
import re
import nltk
from collections import defaultdict
import yaml,json
import numpy as np
import copy
from discourse.doctext import iterdoctext
import codecs
from extract_lexical_cohesion_errors import NOUNS,inserted_in_PE,removed_in_PE, int2error


error_type_all = 0
error_type_lexical = 1
error_type_connectives = 2
error_type_structural = 3

#structural_tag = 'structural'
structural_tag = 'clausal'
clausal_tag = 'clausal'
lexical_tag = 'lexical'
connective_tag = 'connective'
end_tag=1
start_tag=0

def get_tag(name,tag_type, attributes):
    if tag_type == 0:
        if attributes:
            tag='<error type=%s' %name
            for k,v in attributes.items():
                tag+=' %s=%s' %(k,v)
            return tag+'>'
        else:
            return '<error type=%s>' %name
    elif tag_type == 1:
        return '</error>' 
    
def main(args):
    """ Take errors from error file and insert into reference file, with relevant markup. 
    Errors may take various forms. Input may be parsed file or plain text.
PE:
1      after#9#Temporal 
5      but#43#Comparison 
5      as#58#Temporal 
6      because#2#Contingency 
7      Indeed#7#Expansion 
MT:
0      Yet#17#Comparison     
1      when#10#Temporal     
5      but#13#Comparison 
6      because#2#Contingency 
7      Indeed#5#Expansion 
 
  Actual error injected into postedited sentence, which is then replaced in copy of postedited corpus. - in the case of lexical and discourse connective errors. 
  For structural errors entire sentence is replaced. [As MT too distant from REF stylistically.]
  The overall effect is that of isolating discourse errors in the corpus.
    """
    
    pe,mt = get_corpora(args.directory+os.sep+'pe',args.directory+os.sep+'mt')
    inject_errors(pe,mt,args.errors, args.alignments, args.structural, args.connectives, args.output)
    

def inject_errors(pe_txt, mt_txt, errors_dir, structural_error_file, alignments, error_type, output):
    
    markedup_corpus = defaultdict(list)
    injected_corpus = defaultdict(list)
    pe,mt = get_corpora_doctext(pe_txt,mt_txt)
    for docid, lines in pe.iteritems():
        markedup_corpus[int(docid)] = [line.rstrip('\n') for line in pe.get(docid)]
        injected_corpus[int(docid)] = [line.rstrip('\n') for line in pe.get(docid)]
    structural_errors  = {}
    logging.debug('inject_errors.. type=%s', error_type)
    if error_type == error_type_structural or error_type== error_type_all :
        structural_errors  = inject_clausal_errors(pe, mt, structural_error_file, markedup_corpus, injected_corpus, output)
    if error_type == error_type_lexical or error_type== error_type_all :
        alignments_per_doc = inject_lexical_errors(pe, mt, get_errors(errors_dir,'lexical_errors'), alignments, structural_errors, markedup_corpus, injected_corpus, output)
    if error_type == error_type_connectives or error_type== error_type_all :
        inject_discourse_errors(pe, mt, get_errors(errors_dir,'connective_errors'), alignments_per_doc, structural_errors, markedup_corpus, injected_corpus, output)
    #inject_discourse_errors(pe, mt, get_errors(errors_dir,'connective_errors'), yaml.safe_load(open(alignments)), structural_errors, markedup_corpus, injected_corpus, output)
    
    
def get_errors(errors_dir, type):
    return (errors_dir+os.sep+type+'_json')
        
def inject_discourse_errors(pe_docs, mt_docs, discourse_errors, doc_alignments, structural_errors, markedup_corpus, injected_corpus, output):
    """ params: plain text reference file to be injected, post-edited version, machine-translated version, list of errors 
    PE: (S1 (S (S (NP (NP (DT Another) (JJ crucial) (NN step)) (PP (IN for#39#0) (NP (NP (DT the) (NNPS Balkans
    MT: (S1 (S (CC Yet#17#Comparison) (S (NP (NP (DT a) (JJ crucial) (NN step)) (PP (IN for#18#0) (NP (NP (DT the) (NNPS Balkans))
     
    discourse connectives in mt:
    0      Yet#17#Comparison 
    1      when#10#Temporal 
    5      but#13#Comparison 
    pe:
    1      after#9#Temporal 
    5      but#43#Comparison 
    5      as#58#Temporal 
    'Yet' wrongly in MT, deleted in pe -> reinsert 
    'when' becomes 'after' in PE    -> replace
    'as' missing in MT, inserted in PE ->insert
    
    Using list of extracted errors: 
    1. find position of item in MT: find correct line, then locate within line
    2. find new position in PE
    3. insert in PE
    
    connective errors: error list of format below, where doc->line->removed & inserted
    0 = removed : connective in MT but not in PE, so need added to reverse error
    1 = inserted : connectives in PE which are absent in MT, so should be removed to reverse error
    {"1": 
        {"0": {"0": ["Yet"], "1": []}, 
        "1": {"0": ["when"], "1": ["after"]}, 
        "5": {"0": [], "1": ["as"]}, 
        "17": {"0": [], "1": ["in fact", "while"]}, 
        "20": {"0": ["Indeed"], 
        "1": ["In fact"]}, 
        "21": {"0": [], "1": ["and"]}}} """
    """
    {"0": 
        {"0": {"0": ["Yet"], "1": []}, 
        "2": {"0": ["when"], "1": ["after"]}, 
        "6": {"0": [], "1": ["as"]}, 
        "18": {"0": [], "1": ["in fact", "while"]}, 
        "21": {"0": ["Indeed"], "1": ["In fact"]}, 
        "22": {"0": [], "1": ["and"]}}, 
    "1":
         {"24": {"0": [], "1": ["while"]}, 
        "18": {"0": ["so"], "1": ["thus"]}, 
        "19": {"0": [], "1": ["In fact"]}, 
        "6": {"0": ["and"], "1": ["as"]}, 
        "7": {"0": ["and"], "1": []}}}"""
    
    errors = yaml.safe_load(open(discourse_errors))
    for docid, lines in errors.items():
        logging.debug( 'DOCID=%s' %docid)
        for line, error_type in lines.items():
            logging.debug( 'LINE=%s' %line)
            """check if case of insertion and deletion, ie replace: """
            replace = False 
            logging.debug( lines[line])
             
            if not is_structural_error_line(structural_errors, docid, line): 
                
                to_reinsert = lines[line]['0']#[int2error(removed_in_PE)] #removed_in_PE, so reinsert to revert edit
                to_remove = lines[line]['1']#[int2error(inserted_in_PE)]#inserted_in_PE, so remove to revert edit
                if to_reinsert and to_remove:
                    replace = True                
                #logging.debug( 'removed : inserted  ')
                logging.debug( 'reinsert :remove  ')
                logging.debug([w for w in to_reinsert])
                logging.debug([w for w in to_remove])
                line_no = int(line)
                pe_sentence = pe_docs[docid][line_no]
                mt_sentence = mt_docs[docid][line_no]
                logging.debug([w for w in mt_sentence])
                logging.debug([w for w in pe_sentence])
                #print doc_alignments                    
                print doc_alignments[docid][line]#
                mt_words = re.findall(r"[\w']+|[.,!?;]", mt_sentence, re.UNICODE)
                pe_words = re.findall(r"[\w']+|[.,!?;]", pe_sentence, re.UNICODE)
                temp = copy.deepcopy(pe_words)
                injected_corpus[int(docid)][line_no] = temp
                temp = copy.deepcopy(pe_words)
                markedup_corpus[int(docid)][line_no] =temp
                for word in to_reinsert:    
                    logging.debug('WORD=%s type=removed in PE->reinsert to revert' %word) 
                    #for word in words:
                    """ check if the word is there, just wasnt tagged as a relevant POS """
                    if not word in pe_words:
                        """ find position via alignments and check if straight reversion is feasible 
                        get index in mt. get alignment for that index. check aligned word in indexed pe array """
                        for mt_pos, w in enumerate( mt_words):
                            if w == word:
                                word_alignments = doc_alignments[docid][str(line_no)].split()  
                                print word_alignments
                                print 'check for %s ' %mt_pos
                                found = False
                                for idx, a in enumerate(word_alignments):
                                    """ check against first half of alignment, eg 18-21 , as alignments are t2r ie target to ref, ie MT to PE"""
                                    if str(mt_pos)+'-' in a:
                                        logging.debug('found alignment %s at idx %s' %(a,idx))
                                        pe_idx = a.find('-')
                                        found = True
                                        logging.debug( 'aligned to: '+pe_words[int(a[pe_idx+1:])])
                                        logging.debug('from:%s'%(markedup_corpus[int(docid)][line_no]))
                                        injected_corpus[int(docid)][line_no][int(a[pe_idx+1:])] = word
                                        logging.debug('injected corpus now=')
                                        logging.debug([item for item in injected_corpus[int(docid)][line_no]])
                                        #pe_words[int(a[pe_idx+1:])] = tag_error_attributes(connective_tag, word, removed_in_PE, pe_words[int(a[pe_idx+1:])])
                                        """alignment may be thrown due to tags for other errors... """
                                        #tagged_idx = 
                                        markedup_corpus[int(docid)][line_no][int(a[pe_idx+1:])] = tag_error_attributes(connective_tag, word, removed_in_PE, pe_words[int(a[pe_idx+1:])])
                                        logging.debug('tagged corpus now=')
                                        logging.debug([item for item in markedup_corpus[int(docid)][line_no]])
                                        logging.debug('replace='+str(replace))
                                        if replace and word in to_remove:#remove from there while we are at it
                                            logging.debug( 'in inserted list: %s' %word) 
                                            to_remove.remove(word) #tagged[int(a[pe_idx+1:])][1])                                    
                                        #markedup_corpus[int(docid)][line_no] =(' '.join(temp))
                                        break
                                if not found:
                                    logging.debug( 'not found %s' %mt_pos)
                                    if mt_pos == 0:#null at start
                                        
                                        logging.debug('from:%s')# %(markedup_corpus[int(docid)][line_no]))
                                        logging.debug([item for item in markedup_corpus[int(docid)][line_no]])
                                        logging.debug('now:%s'%(tag_error_attributes(connective_tag, word, removed_in_PE, "")))
                                        injected_corpus[int(docid)][line_no].insert(0, word)
                                        markedup_corpus[int(docid)][line_no].insert(0, word)
                                        
                #for word in to_remove:
                if to_remove:
                    #elif int(error_type) == inserted_in_PE:
                    logging.debug( 'type=insert in PE->remove to revert: ')
                    #for word in words:                    
                    logging.debug([w for w in to_remove])
                    #temp = copy.deepcopy(pe_words)
                    temp = [tag_error_attributes(connective_tag," ","del", word) if word in to_remove else word for word in markedup_corpus[int(docid)][line_no]]
                    temp2 =[ word for word in injected_corpus[int(docid)][line_no] if word not in to_remove]
                    #temp = [tag_error_attributes(connective_tag," ","del", word) if word in to_remove else word for word in pe_words]
                    logging.debug('injected corpus now='+' '.join(temp2))
                    #logging.debug([item for item in injected_corpus[int(docid)][line_no]])
                    logging.debug('markedup corpus now='+' '.join(temp))
                    logging.debug([item for item in markedup_corpus[int(docid)][line_no]])
                    tag_error_attributes(connective_tag," ","del", word)                     
                    markedup_corpus[int(docid)][line_no] = (' '.join(temp))
                    injected_corpus[int(docid)][line_no] = (' '.join(temp2))
    print_corpus(markedup_corpus, output+'.tagged')
    print_corpus(injected_corpus, output)
    
def get_corpora_doctext(pe_text, mt_text):
    pe_docs = defaultdict(list)
    mt_docs = defaultdict(list)
    #with codecs.open(os.path.join(pe_text, filename),"r","utf-8") as pe_doc:
    print pe_text, mt_text
    with codecs.open(pe_text,"r","utf-8") as pe_doc:
        docid = 0
    #with open(pe_text, 'r') as pe_doc:
        #for line in open(args.input, 'r'):
        
        for line in pe_doc:
            if line.startswith('#'):
                idx = line.find('id=')
                #temp = idx+1:
                docid = line[idx+3:].strip()
                print 'docid='+docid.strip()+'#'
                pe_docs[docid] = []
        #pe_lines = pe_doc.readlines()
            else:
                pe_docs[docid].append(line)
        #pe_docs[docid[0]] = pe_lines
    with codecs.open(mt_text,"r","utf-8") as mt_doc:
        docid = 0
        for line in mt_doc:
            if line.startswith('#'):
                idx = line.find('id=')
                #temp = idx+1:
                docid = line[idx+3:].strip()
                mt_docs[docid] = []
            else:
        #pe_lines = pe_doc.readlines()
                mt_docs[docid].append(line)
    logging.debug('CORPORA **********')
     
    return pe_docs, mt_docs

def get_corpora(pe_text, mt_text):
    
    #mt_docs = list(iterdoctext(args.input))
    #pe_docs = list(iterdoctext(args.input))
    
    pe_docs = defaultdict(list)
    mt_docs = defaultdict(list)
    files = [name for name in os.listdir(pe_text) if os.path.isfile(os.path.join(pe_text, name)) ]
    for filename in files:
        logging.info(filename)
        #with open(os.path.join(pe_text, filename)) as pe_doc:
        with codecs.open(os.path.join(pe_text, filename),"r","utf-8") as pe_doc:
            pe_lines = pe_doc.readlines()
            docid =re.findall("\d+",filename)
            print docid[0]
            
            pe_docs[docid[0]] = pe_lines#[line.rstrip() for line in pe_lines]
                
    MT_files = [name for name in os.listdir(mt_text) if os.path.isfile(os.path.join(mt_text, name)) ]
    for mt_filename in MT_files: 
        logging.info(mt_filename) 
        #with open(os.path.join(mt_text, mt_filename))as mt_doc:
        with codecs.open(os.path.join(mt_text, mt_filename),"r","utf-8")as mt_doc:
            mt_lines = mt_doc.readlines()
            docid =re.findall("\d+",mt_filename)
            print docid[0]
            mt_docs[docid[0]] = mt_lines
    #print mt_lines
    #return pe_lines, mt_lines
    print pe_docs
    print mt_docs
    return pe_docs, mt_docs
            
def inject_clausal_errors(pe, mt, structural_errors, markedup_corpus, injected_corpus, output):
    """ clausal errors:
    errors where clausal restructuring has occured to a level deemed relevant for discourse relational errors 
    For each document:  1. extract each error line
                        2. find equivalent line in MT and extract
                        3. find equivalent line in PE and replace
    """
    
    
    doc_errors = json.load(open(structural_errors))
    for docid, lines in doc_errors.items():
        #docid = re.findall("\d+",doc)
        print 'structural error at '+docid
        print lines
        #markedup_corpus[int(docid)] = [line.rstrip('\n') for line in pe.get(docid)]
        #markedup_corpus[int(docid)] = pe.get(docid)
        print pe[docid]
        print mt[docid]
        print mt
        for line in doc_errors.get(docid):
        #for line, alignments in lines:
            print line
            line_no = int(line)
            print 'replace line %s'%line_no
            print pe[docid][line_no].rstrip()
            print mt[docid][line_no].rstrip()
            pe[docid][line_no]= mt[docid][line_no]
            
            injected_corpus[int(docid)][line_no]= mt[docid][line_no].rstrip()
            markedup_corpus[int(docid)][line_no]= tag_error(structural_tag, mt[docid][line_no].rstrip())
            
    print markedup_corpus
    #print_markedup_corpus(markedup_corpus, output)
    print_corpus(markedup_corpus, output+'.tagged')
    print_corpus(injected_corpus, output)
    return doc_errors

def print_corpus(corpus, output):    
    #logging.debug('printing corpus to '+output)
    print 'printing corpus to '+output
    with codecs.open(output, 'w', encoding="utf-8") as fo:
        for docid in sorted(corpus.keys()):#   , cmp=numeric_compare)
            fo.write("# id="+str(docid)+'\n')
            for line in  corpus[int(docid)]:
                #print line
                if type(line) is list: 
                    for item in line:
                        fo.write(item+' ')
                    fo.write('\n')
                else:
                        fo.write(line+'\n')

def read_alignments(istream):
    #return [np.array([[str2int[role] for role in line] for line in lines], int) for lines, attrs in iterdoctext(istream)]
    return [np.array([[ alignment for alignment in line] for line in lines], int) for lines, attrs in iterdoctext(istream)]
    

def tag_error(error_tag, content):
    return get_tag(error_tag,start_tag, None)+content+get_tag(error_tag,end_tag, None)
        
def tag_error_attributes(error_tag, content, error_type, item):
    attributes={'edit':error_type,'item':item}
    return ' '+get_tag(error_tag,start_tag,attributes)+content+get_tag(error_tag,end_tag,attributes)+' '

def inject_lexical_errors(pe_docs, mt_docs, error_file, alignments, structural_errors, markedup_corpus, injected_corpus, output):
    """ 
    Using list of extracted errors: 
    1. find position of item in MT: find correct line, then locate within line
    2. find new position in PE
    3. replace in PE
    
    lexical errors: error list of format below, where 
    0 = removed : nouns in MT but not in PE, so need added to reverse error
    1 = inserted : nouns in PE which are absent in MT, so should be removed to reverse error
    doc_1    32    [0, ['tant']]
    doc_1    2    [1, ['United', 'States']]
    doc_1    5    [1, ['UN', 'fact']]
    doc_1    6    [1, ['Serbian']] 
    """
    logging.debug('LEXICAL ERRORS:')
    #doc_alignments_ = json.load(open(alignments))
    doc_alignments = yaml.safe_load(open(alignments))
    errors = yaml.safe_load(open(error_file))#+'_json'))
    #lines = istream.readlines()
    for docid, lines in errors.items():
        print 'DOCID=%s' %docid
        for line, error_type in lines.items():
            print 'LINE=%s' %line
            """check if case of insertion and deletion, ie replace: """
            replace = False 
            print lines[line] 
            if not is_structural_error_line(structural_errors, docid, line): 
                
                to_reinsert = lines[line]['0']#[int2error(removed_in_PE)] #removed_in_PE, so reinsert to revert edit
                to_remove = lines[line]['1']#[int2error(inserted_in_PE)]#inserted_in_PE, so remove to revert edit
                if to_reinsert and to_remove:
                    replace = True
                #for error_type, words in error_type.items():
                #logging.debug( 'removed : inserted  ')
                logging.debug( 'reinsert :remove -nouns- ')
                logging.debug([item for item in to_reinsert])
                logging.debug([item for item in to_remove])
                line_no = int(line)
                pe_sentence = pe_docs[docid][line_no]
                mt_sentence = mt_docs[docid][line_no]
                logging.debug('MT='+ mt_sentence)
                logging.debug('PE='+pe_sentence)                    
                logging.debug( doc_alignments[docid][str(line_no)])#)
                mt_words = re.findall(r"[\w']+|[.,!?;]", mt_sentence, re.UNICODE)
                pe_words = re.findall(r"[\w']+|[.,!?;]", pe_sentence, re.UNICODE)
                temp = copy.deepcopy(pe_words)
                injected_corpus[int(docid)][line_no] = temp
                temp = copy.deepcopy(pe_words)
                markedup_corpus[int(docid)][line_no] =temp
                for word in to_reinsert:
                    print 'WORD=%s type=removed in PE->reinsert to revert' %word
                    """ check if hyphenated- if so take pair as whole...  match on first only"""
                    if '-' in word:
                        words =  word.split('-')
                        word = ''.join(words)
                    """check if word is in fact there, just that POS tag not recorded as noun """                     
                    if word not in mt_words:
                        logging.debug( word +' not in list')
                        break
                    """ find position via alignments and check if straight reversion is feasible 
                    get index in mt. get alignment for that index. check aligned word in indexed pe array """
                    for mt_pos, w in enumerate( mt_words):
                        logging.debug( word +' and '+w+ ' test='+str(w == word)+' or '+str(w is word))
                        if w == word:
                            logging.debug('finding alignment for '+word)
                            word_alignments = doc_alignments[docid][str(line_no)].split()  
                            for idx, a in enumerate(word_alignments):
                                """ check against first half of alignment, eg 18-21 """
                                alignments = a.split('-')
                                print 'alignments = '+alignments[1]+' mtpos='+str(mt_pos)
                                if mt_pos == int(alignments[1]):
                                #if str(mt_pos)+'-' in a:
                                    logging.debug( 'found alignment %s at idx %s' %(a,idx))
                                    pe_idx = a.find('-')
                                    logging.debug( str(int(a[pe_idx+1:]) ))
                                    """ get POS to check if aligns to another noun """
                                    tagged = nltk.pos_tag(nltk.word_tokenize(pe_sentence))
                                    
                                    if len(tagged) > int(a[pe_idx+1:]) and len(pe_words) > int(a[pe_idx+1:]):
                                        #print tagged[int(a[pe_idx+1:])]
                                        logging.debug( tagged[int(a[pe_idx+1:])][1])
                                        #print tagged[int(a[pe_idx+1:])][1] in  NOUNS
                                        if tagged[int(a[pe_idx+1:])][1] in  NOUNS:
                                            logging.debug('replacing noun directly:')
                                            logging.debug('from:%s'%(markedup_corpus[int(docid)][line_no]))
                                            #logging.debug('now:%s'%(tag_error_attributes(lexical_tag, word, removed_in_PE, pe_words[int(a[pe_idx+1:])])))
                                            logging.debug('now:%s'%(tag_error_attributes(lexical_tag, word, removed_in_PE, pe_words[int(a[pe_idx+1:])])))
                                            injected_corpus[int(docid)][line_no][int(a[pe_idx+1:])] = word
                                            
                                            if replace and pe_words[int(a[pe_idx+1:])] in to_remove:#remove from there while we are at it
                                                logging.debug( 'in inserted list: %s' %(tagged[int(a[pe_idx+1:])][1])) 
                                                #to_remove.remove(tagged[int(a[pe_idx+1:])][1])
                                                to_remove.remove(pe_words[int(a[pe_idx+1:])])
                                            markedup_corpus[int(docid)][line_no][int(a[pe_idx+1:])] =  tag_error_attributes(lexical_tag, word, removed_in_PE, pe_words[int(a[pe_idx+1:])])
                                            
                                        else:
                                            """ if not noun, find nearest noun for replacing """
                                            nearest_noun, nn_idx =  get_nearest_noun(tagged, pe_words, a[pe_idx+1:], w)
                                            logging.debug( "nearest noun to replace = "+ nearest_noun)
                                            logging.debug([w for w in pe_words])
                                            #print tag_error_attributes(lexical_tag, nearest_noun, 'ins', word)
                                            logging.debug('from:%s'%(markedup_corpus[int(docid)][line_no]))
                                            logging.debug( 'replacing with %s'%(tag_error_attributes(lexical_tag, word,"ins" , nearest_noun)))
                                            print '%s in %s' %( nn_idx, len(pe_words))
                                            #if len(pe_words) <=   nn_idx and (nn_idx-len(pe_words)) < 2:
                                            #    """ index is higher than array it is inserting into, due to discrepancies in punctuation, but close to end """
                                            #    injected_corpus[int(docid)][line_no].append( word)
                                            #    markedup_corpus[int(docid)][line_no].append(tag_error_attributes(lexical_tag, word, "ins"  , nearest_noun))
                                            #elif len(pe_words) < nn_idx and (nn_idx-len(pe_words)) > 2:
                                            """index is higher than array it is inserting into, due to discrepancies in punctuation, so give up on this one """
                                            #else:
                                            injected_corpus[ int(docid)][line_no][nn_idx] =word
                                            markedup_corpus[int(docid)][line_no][nn_idx] = tag_error_attributes(lexical_tag, word, "ins"  , nearest_noun)
                                            if replace and nearest_noun in to_remove:#remove from there while we are at it
                                                print 'in inserted list: %s' %nearest_noun 
                                                to_remove.remove(nearest_noun)
                                            
                            #logging.debug('done with word '+word+' : result-')  
                            logging.debug([w for w in markedup_corpus[int(docid)][line_no]]) 
                            break    
                    #logging.debug('done with word '+word+' : result-')  
                    #break            
                #for word in to_remove:
                logging.debug([w for w in to_remove])
                if to_remove:
                    #elif int(error_type) == inserted_in_PE:
                    logging.debug( 'type=insert in PE->remove to revert')
                    temp = [tag_error_attributes(lexical_tag,"","del",word) if word in to_remove else word for word in markedup_corpus[int(docid)][line_no]]
                    markedup_corpus[int(docid)][line_no] = temp#(' '.join(temp))
                    temp2 = [word for word in injected_corpus[int(docid)][line_no]  if word not in to_remove]
                    injected_corpus[int(docid)][line_no] = temp2#(' '.join(temp2))
                    logging.debug(markedup_corpus[int(docid)][line_no])
    print_corpus(markedup_corpus, output+'.tagged')
    print_corpus(injected_corpus, output)
    return doc_alignments
    
def get_alignment(doc_alignments, doc_id):
    
    for doc, alignments in doc_alignments.items():
        if doc==doc_id:
            return alignments
    return None
                    
def get_nearest_noun(tagged, pe_words, pe_idx, word):
    #sprint 'get_nearest_noun , idx=%s '%pe_idx
    close_nouns = defaultdict(list)
    for idx, pos in enumerate(tagged):
        #print 'checking %s , %s ' %(pos[0],pos[1])
        #if word in pos[0]:
        #    print 'found POS for match- %s' %pos[0]
        #    return pos 
        if pos[1] in NOUNS:
            #print 'found noun..%s' %pos[0]
            close_nouns[idx] =pos[0]
        #print close_nouns
    if close_nouns:
        idx =  min(close_nouns, key=lambda x:abs(x-int(pe_idx)))
        #print 'considering returning %d'%idx
        #print close_nouns[idx]
        if idx > len(pe_idx):
            return word,int(pe_idx) 
        return close_nouns[idx], int(idx)
    else:
        return word,int(pe_idx)
                         
def is_structural_error_line(structural_errors, docid_to_match, line_to_match):
    for docid, lines in structural_errors.items():
        if docid == docid_to_match:
            for line in lines:
                if line == line_to_match:
                    return True
    return False
def argparser():
    """parse command line arguments"""
    
    parser = argparse.ArgumentParser(description='Remove the leading alphanumeric from each line.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('directory', nargs='?',
                        type=str, 
                        help='input directory')
    parser.add_argument('--errors', nargs='?',
                        type=str, 
                        help='error list')
    parser.add_argument('--structural', nargs='?',
                        type=str, 
                        help='structural error list')
    parser.add_argument('--alignments', nargs='?',
                        type=str, 
                        help='alignments for MT-PE hter edits, doc separated')
    parser.add_argument('--connectives', nargs='?',
                        type=str, 
                        help='--connectives error list')
    parser.add_argument('--output', nargs='?',
                        type=str, 
                        help='output directory')
    parser.add_argument('--verbose', '-v',
            action='store_true',
            help='increase the verbosity level')
    parser.add_argument('--logfile', nargs='?',
                        type=str, 
                        help='logfile directory')
    
    args = parser.parse_args()
    
    logging.basicConfig(filename=args.logfile,filemode='a',
                            format='%(asctime)s,%(msecs)d %(levelname)s %(message)s',
                            datefmt='%H:%M',
            level=(logging.DEBUG if args.verbose else logging.INFO))#, 
            #format='%(levelname)s %(message)s')
    return args

if __name__ == '__main__':
    main(argparser())