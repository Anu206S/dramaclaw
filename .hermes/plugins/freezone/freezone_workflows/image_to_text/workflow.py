WORKFLOW = {
    "order": 8,
    "workflow_type": "image_to_text",
    "label": "图生文",
    "aliases": ["img2text", "i2t", "图生文", "图片生成文本"],
    "template_kind": "simple",
    "title": "图生文工作流",
    "nodes": [
        (
            "image_input",
            "imageGenNode",
            "图片输入",
            "承载上传图片或已生成图片，作为文本分析的源素材。",
            "image",
        ),
        (
            "text_output",
            "textAnnotationNode",
            "生成文本",
            "根据上游图片生成描述、提示词、文案或分析文本。",
            "story",
        ),
    ],
    "edges": [("image_input", "text_output")],
}
