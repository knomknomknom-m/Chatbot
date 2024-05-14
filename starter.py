import streamlit as st

from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import ChatMessage

from dotenv import load_dotenv

load_dotenv()

# handle streaming conversation
class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text)


# function to extract text from an HWP file
import olefile
import zlib
import struct

def get_hwp_text(filename):  # hwp파일을 다루고 싶으면 이코드 사용
    f = olefile.OleFileIO(filename)
    dirs = f.listdir()

    # HWP 파일 검증
    if ["FileHeader"] not in dirs or \
       ["\x05HwpSummaryInformation"] not in dirs:
        raise Exception("Not Valid HWP.")

    # 문서 포맷 압축 여부 확인
    header = f.openstream("FileHeader")
    header_data = header.read()
    is_compressed = (header_data[36] & 1) == 1

    # Body Sections 불러오기
    nums = []
    for d in dirs:
        if d[0] == "BodyText":
            nums.append(int(d[1][len("Section"):]))
    sections = ["BodyText/Section"+str(x) for x in sorted(nums)]

    # 전체 text 추출
    text = ""
    for section in sections:
        bodytext = f.openstream(section)
        data = bodytext.read()
        if is_compressed:
            unpacked_data = zlib.decompress(data, -15)
        else:
            unpacked_data = data
    
        # 각 Section 내 text 추출    
        section_text = ""
        i = 0
        size = len(unpacked_data)
        while i < size:
            header = struct.unpack_from("<I", unpacked_data, i)[0]
            rec_type = header & 0x3ff
            rec_len = (header >> 20) & 0xfff

            if rec_type in [67]:
                rec_data = unpacked_data[i+4:i+4+rec_len]
                section_text += rec_data.decode('utf-16')
                section_text += "\n"

            i += 4 + rec_len

        text += section_text
        text += "\n"

    return text

# Function to extract text from an PDF file
from pdfminer.high_level import extract_text

def get_pdf_text(filename):
    raw_text = extract_text(filename)
    return raw_text

# document preprocess
def process_uploaded_file(uploaded_file):  # 
    # Load document if file is uploaded
    if uploaded_file is not None:
        # loader
        # pdf파일을 처리하려면?
        if uploaded_file.type == 'application/pdf':
            raw_text = get_pdf_text(uploaded_file)
        # hwp파일을 처리하려면? (hwp loader(parser)는 난이도 매우 어려움)
        elif uploaded_file.type == 'application/octet-stream':
            raw_text = get_hwp_text(uploaded_file)

        
        # splitter
        text_splitter = CharacterTextSplitter(
            separator = "\n\n",
            chunk_size = 1500,
            chunk_overlap  = 300,
            length_function = len,
            is_separator_regex = False,
        )
        all_splits = text_splitter.create_documents([raw_text])
        
        print("총 " + str(len(all_splits)) + "개의 passage")
        
        # storage
        vectorstore = FAISS.from_documents(documents=all_splits, embedding=OpenAIEmbeddings())
        
        return vectorstore, raw_text
    return None

# generate response using RAG technic
def generate_response(query_text, vectorstore, callback):

    # retriever 
    docs_list = vectorstore.similarity_search(query_text, k=3)
    docs = ""
    for i, doc in enumerate(docs_list):
        docs += f"'문서{i+1}':{doc.page_content}\n"
    
    # generator
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0, streaming=True, callbacks=[callback])
    
    # chaining
    rag_prompt = [
    SystemMessage(
        content="너는 문서에 대해 질의응답을 하는 '박사님'야. 주어진 문서를 참고하여 사용자의 질문에 답변을 해줘. 문서에 내용이 정확하게 나와있지 않으면 아는 지식 선에서 잘 대답해줘. 최대한 쉬운 단어를 사용해서 설명해줘. 가끔씩 이모티콘을 사용해도 돼. 답변이 어려운게 있을 때는 단계별로 알려줘. 잘 대답하면 팁으로 200달러를 줄게"
    ),
    HumanMessage(
        content=f"질문:{query_text}\n\n{docs}"
    ),
    ]

    response = llm(rag_prompt)

    return response.content


def generate_summarize(raw_text, callback):
    # generator 
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0, streaming=True, callbacks=[callback])
    
    # prompt formatting
    rag_prompt = [
        SystemMessage(
            content="다음 나올 문서를 'Bullet style'로 요약해줘. 중요한 내용만."
        ),
        HumanMessage(
            content=raw_text
        ),
    ]
    
    response = llm(rag_prompt)
    return response.content


# page title
st.set_page_config(page_title='📝논문을 쉽게 알려주는 선생님📑')
st.title('📝논문을 쉽게 알려주는 선생님📑')

# 사용자 정의 CSS 적용
def apply_custom_css():
    custom_css = """
    <style>
        body {
            background-color: #B3E0F2;  /* 보노보노의 파스텔 블루 색상 */
            color: #000000;
        }
        .stApp {
            background-color: #B3E0F2;  /* 보노보노의 파스텔 블루 색상 */
        }
        .stButton>button {
            background-color: #72C6E1;  /* 버튼 색상 */
            color: #FFFFFF;
            border-radius: 10px;
            border: none;
        }
        .stTextInput>div>div>input {
            background-color: #E6F7FF;  /* 입력창 배경 색상 */
            color: #000000;
            border-radius: 10px;
            border: 1px solid #72C6E1;
        }
        .stMarkdown {
            color: #333333;
        }
        .css-1aumxhk {
            background-color: #72C6E1;  /* 채팅 메시지 배경 색상 */
        }
        .css-1d391kg p {
            color: #000000;
        }
        .css-1d391kg {
            background-color: #E6F7FF;  /* 채팅 메시지 입력 배경 색상 */
            border-radius: 10px;
            padding: 10px;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

apply_custom_css()

# 보노보노 그림 추가
st.image('D:/Users/mkw81/Desktop/4.jpeg', width='300')


# enter token
import os
api_key = st.sidebar.text_input("Enter your OpenAI API Key", type="password")
save_button = st.sidebar.button("Save Key")
if save_button and len(api_key)>10:
    os.environ["OPENAI_API_KEY"] = api_key
    st.sidebar.success("API Key saved successfully!")

# file upload
uploaded_file = st.file_uploader('Upload an document', type=['hwp','pdf'])

# file upload logic
if uploaded_file:
    vectorstore, raw_text = process_uploaded_file(uploaded_file)
    if vectorstore:
        st.session_state['vectorstore'] = vectorstore
        st.session_state['raw_text'] = raw_text
        
# chatbot greatings
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        ChatMessage(
            role="assistant", content=("대졸한테 물어보지 말고 박사한테 물어봐⭐.\n\n"
                           "문서 이해를 도와줄 챗봇 박사님입니다. 오늘은 어떤 논문을 읽을 건가요?")

        )
    ]

# conversation history print 
for msg in st.session_state.messages:
    st.chat_message(msg.role).write(msg.content)
    
# message interaction
if prompt := st.chat_input("'요약'이라고 입력해보세요!"):
    st.session_state.messages.append(ChatMessage(role="user", content=prompt))
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        stream_handler = StreamHandler(st.empty())
        
        if prompt == "요약":
            response = generate_summarize(st.session_state['raw_text'],stream_handler)
            st.session_state["messages"].append(
                ChatMessage(role="assistant", content=response)
            )
        
        else:
            response = generate_response(prompt, st.session_state['vectorstore'], stream_handler)
            st.session_state["messages"].append(
                ChatMessage(role="assistant", content=response)
            )
