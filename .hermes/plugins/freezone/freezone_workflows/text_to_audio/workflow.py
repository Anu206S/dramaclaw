WORKFLOW = {
    "order": 9,
    "workflow_type": "text_to_audio",
    "label": "文生音频",
    "aliases": ["txt2audio", "t2a", "文生音频", "文本生成音频"],
    "template_kind": "simple",
    "title": "文生音频工作流",
    "nodes": [
        (
            "text_prompt",
            "textAnnotationNode",
            "音频文本",
            "输入口播、对白、旁白或音频生成文本。",
            "input",
        ),
        ("audio_output", "audioNode", "生成音频", "根据上游文本生成音频。", "audio"),
    ],
    "edges": [("text_prompt", "audio_output")],
}
