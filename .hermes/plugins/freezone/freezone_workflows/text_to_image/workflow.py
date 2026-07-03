WORKFLOW = {
    "order": 5,
    "workflow_type": "text_to_image",
    "label": "文生图",
    "aliases": ["txt2img", "t2i", "文生图", "文本生成图片"],
    "template_kind": "simple",
    "title": "文生图工作流",
    "nodes": [
        (
            "text_prompt",
            "textAnnotationNode",
            "文本提示词",
            "输入图片生成所需的主体、风格、构图和细节。",
            "input",
        ),
        ("image_output", "imageGenNode", "生成图片", "根据上游文本提示词生成图片。", "image"),
    ],
    "edges": [("text_prompt", "image_output")],
}
