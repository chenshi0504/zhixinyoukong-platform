"""
文本分块器
将长文档分割成适合向量化的小块
"""

import re
from typing import List, Dict
from .document_loader import Document


class TextSplitter:
    """文本分块器基类"""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """分割文本"""
        raise NotImplementedError

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """分割文档列表"""
        chunks = []
        for doc in documents:
            text_chunks = self.split_text(doc.content)
            for i, chunk in enumerate(text_chunks):
                chunk_metadata = doc.metadata.copy()
                chunk_metadata['chunk_id'] = i
                chunk_metadata['total_chunks'] = len(text_chunks)
                chunks.append(Document(content=chunk, metadata=chunk_metadata))
        return chunks


class RecursiveCharacterTextSplitter(TextSplitter):
    """递归字符文本分块器"""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, separators: List[str] = None):
        super().__init__(chunk_size, chunk_overlap)
        self.separators = separators or ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

    def split_text(self, text: str) -> List[str]:
        """递归分割文本"""
        return self._split_text_recursive(text, self.separators)

    def _split_text_recursive(self, text: str, separators: List[str]) -> List[str]:
        """递归分割"""
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        # 尝试使用当前分隔符
        separator = separators[0] if separators else ""

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # 合并小块
        chunks = []
        current_chunk = []
        current_length = 0

        for split in splits:
            split_length = len(split)

            if current_length + split_length > self.chunk_size and current_chunk:
                # 当前块已满，保存并开始新块
                chunk_text = separator.join(current_chunk)
                chunks.append(chunk_text)

                # 保留重叠部分
                overlap_start = max(0, len(current_chunk) - 1)
                current_chunk = current_chunk[overlap_start:]
                current_length = sum(len(c) for c in current_chunk)

            current_chunk.append(split)
            current_length += split_length

        # 添加最后一块
        if current_chunk:
            chunks.append(separator.join(current_chunk))

        # 如果还有块太大，使用下一个分隔符递归分割
        if len(separators) > 1:
            final_chunks = []
            for chunk in chunks:
                if len(chunk) > self.chunk_size:
                    final_chunks.extend(self._split_text_recursive(chunk, separators[1:]))
                else:
                    final_chunks.append(chunk)
            return final_chunks

        return chunks


class MarkdownTextSplitter(TextSplitter):
    """Markdown文本分块器，按标题层级分割"""

    def split_text(self, text: str) -> List[str]:
        """按Markdown标题分割"""
        # 按标题分割
        header_pattern = r'^(#{1,6})\s+(.+)$'
        lines = text.split('\n')

        chunks = []
        current_chunk = []
        current_headers = []

        for line in lines:
            match = re.match(header_pattern, line)

            if match:
                # 遇到新标题
                if current_chunk:
                    # 保存当前块
                    chunk_text = '\n'.join(current_chunk)
                    if len(chunk_text.strip()) > 0:
                        chunks.append(chunk_text)
                    current_chunk = []

                # 更新标题层级
                level = len(match.group(1))
                title = match.group(2)

                # 保留上级标题
                current_headers = [h for h in current_headers if h[0] < level]
                current_headers.append((level, title))

                # 添加标题上下文
                for h_level, h_title in current_headers:
                    current_chunk.append('#' * h_level + ' ' + h_title)
            else:
                current_chunk.append(line)

            # 检查块大小
            if len('\n'.join(current_chunk)) > self.chunk_size:
                chunk_text = '\n'.join(current_chunk)
                chunks.append(chunk_text)
                current_chunk = []

        # 添加最后一块
        if current_chunk:
            chunk_text = '\n'.join(current_chunk)
            if len(chunk_text.strip()) > 0:
                chunks.append(chunk_text)

        return chunks


class CodeTextSplitter(TextSplitter):
    """代码文本分块器，按函数/类分割"""

    def split_text(self, text: str) -> List[str]:
        """按代码结构分割"""
        # Python函数/类分割
        pattern = r'((?:class|def)\s+\w+.*?:(?:\n(?:    |\t).*)*)'
        matches = re.finditer(pattern, text, re.MULTILINE)

        chunks = []
        last_end = 0

        for match in matches:
            # 添加函数/类之间的内容
            if match.start() > last_end:
                between = text[last_end:match.start()].strip()
                if between:
                    chunks.append(between)

            # 添加函数/类
            code_block = match.group(0)
            if len(code_block) > self.chunk_size:
                # 如果单个函数太大，按行分割
                lines = code_block.split('\n')
                current = []
                for line in lines:
                    current.append(line)
                    if len('\n'.join(current)) > self.chunk_size:
                        chunks.append('\n'.join(current))
                        current = []
                if current:
                    chunks.append('\n'.join(current))
            else:
                chunks.append(code_block)

            last_end = match.end()

        # 添加剩余内容
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                chunks.append(remaining)

        return chunks if chunks else [text]
