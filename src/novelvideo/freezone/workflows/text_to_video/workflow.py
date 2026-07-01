WORKFLOW = {
    "order": 7,
    "workflow_type": "text_to_video",
    "label": "文生视频",
    "aliases": ["txt2video", "t2v", "文生视频", "文本生成视频"],
    "template_kind": "simple",
    "title": "文生视频工作流",
    "nodes": [
        (
            "text_prompt",
            "textAnnotationNode",
            "视频文本提示词",
            "输入视频生成所需的画面、动作、风格和镜头要求。",
            "input",
        ),
        ("image_keyframe", "imageGenNode", "生成关键图", "先根据上游文本生成关键画面。", "image"),
        ("video_output", "videoNode", "生成视频", "再根据关键图生成视频片段。", "video"),
    ],
    "edges": [("text_prompt", "image_keyframe"), ("image_keyframe", "video_output")],
}
