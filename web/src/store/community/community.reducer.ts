import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import {
    fetchCommunityPosts,
    createCommunityPost,
    toggleLikeCommunityPost,
    toggleSaveCommunityPost,
    addCommunityComment,
    deleteCommunityComment,
    deleteCommunityPost,
} from "./community.api";

export interface CommentItem {
    id: string;
    postId?: string;
    userId?: number;
    authorName: string;
    authorAvatar?: string | null;
    authorBadge?: string;
    content: string;
    createdAt: string;
    likes: number;
}

export interface CommunityPost {
    id: string;
    userId?: number;
    authorName: string;
    authorAvatar?: string | null;
    authorRole?: string;
    authorBadge?: "Chuyên gia" | "AI Analyst" | "VIP Trader" | "Thành viên" | string;
    title?: string;
    content: string;
    symbol?: string;
    stance?: "BUY" | "SELL" | "HOLD" | "ANALYSIS" | string;
    targetPrice?: number;
    stopLossPrice?: number;
    category: "hot" | "signal" | "technical" | "fundamental" | "qa" | string;
    sector?: string;
    imageUrl?: string;
    createdAt: string;
    likes: number;
    commentsCount: number;
    viewsCount: number;
    isLiked?: boolean;
    isSaved?: boolean;
    comments: CommentItem[];
}

interface CommunityState {
    posts: CommunityPost[];
    total: number;
    loading: boolean;
    posting: boolean;
    commenting: boolean;
    error: string | null;
}

// Realtime events can arrive before or after the HTTP response for the same
// action, so every insert/remove below is idempotent.
function upsertPost(state: CommunityState, post: CommunityPost, preferIncoming: boolean) {
    const index = state.posts.findIndex((p) => p.id === post.id);
    if (index === -1) {
        state.posts.unshift(post);
        state.total += 1;
    } else if (preferIncoming) {
        state.posts[index] = { ...state.posts[index], ...post };
    }
}

function removePost(state: CommunityState, postId: string) {
    const before = state.posts.length;
    state.posts = state.posts.filter((p) => p.id !== postId);
    if (state.posts.length < before) state.total = Math.max(0, state.total - 1);
}

function addComment(state: CommunityState, postId: string, comment: CommentItem) {
    const post = state.posts.find((p) => p.id === postId);
    if (!post || post.comments.some((c) => c.id === comment.id)) return;
    post.comments.push(comment);
    post.commentsCount += 1;
}

function removeComment(state: CommunityState, postId: string, commentId: string) {
    const post = state.posts.find((p) => p.id === postId);
    if (!post || !post.comments.some((c) => c.id === commentId)) return;
    post.comments = post.comments.filter((c) => c.id !== commentId);
    post.commentsCount = Math.max(0, post.commentsCount - 1);
}

const initialState: CommunityState = {
    posts: [],
    total: 0,
    loading: false,
    posting: false,
    commenting: false,
    error: null,
};

export const communitySlice = createSlice({
    name: "community",
    initialState,
    reducers: {
        optimisticToggleLike: (state, action: PayloadAction<{ postId: string }>) => {
            const post = state.posts.find((p) => p.id === action.payload.postId);
            if (post) {
                post.isLiked = !post.isLiked;
                post.likes = post.isLiked ? post.likes + 1 : Math.max(0, post.likes - 1);
            }
        },
        optimisticToggleSave: (state, action: PayloadAction<{ postId: string }>) => {
            const post = state.posts.find((p) => p.id === action.payload.postId);
            if (post) {
                post.isSaved = !post.isSaved;
            }
        },
        postReceived: (state, action: PayloadAction<CommunityPost>) => {
            upsertPost(state, action.payload, false);
        },
        postRemoved: (state, action: PayloadAction<{ postId: string }>) => {
            removePost(state, action.payload.postId);
        },
        postLikesChanged: (state, action: PayloadAction<{ postId: string; likesCount: number }>) => {
            const post = state.posts.find((p) => p.id === action.payload.postId);
            if (post) post.likes = action.payload.likesCount;
        },
        commentReceived: (state, action: PayloadAction<CommentItem & { postId: string }>) => {
            addComment(state, action.payload.postId, action.payload);
        },
        commentRemoved: (state, action: PayloadAction<{ postId: string; commentId: string }>) => {
            removeComment(state, action.payload.postId, action.payload.commentId);
        },
    },
    extraReducers: (builder) => {
        // Fetch posts
        builder
            .addCase(fetchCommunityPosts.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchCommunityPosts.fulfilled, (state, action) => {
                state.loading = false;
                state.posts = action.payload?.posts || [];
                state.total = action.payload?.total || 0;
            })
            .addCase(fetchCommunityPosts.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        // Create post
        builder
            .addCase(createCommunityPost.pending, (state) => {
                state.posting = true;
            })
            .addCase(createCommunityPost.fulfilled, (state, action) => {
                state.posting = false;
                if (action.payload) upsertPost(state, action.payload, true);
            })
            .addCase(createCommunityPost.rejected, (state, action) => {
                state.posting = false;
                state.error = action.payload as string;
            });

        // Toggle like sync
        builder.addCase(toggleLikeCommunityPost.fulfilled, (state, action) => {
            const { postId, isLiked, likesCount } = action.payload;
            const post = state.posts.find((p) => p.id === postId);
            if (post) {
                post.isLiked = isLiked;
                if (typeof likesCount === "number") {
                    post.likes = likesCount;
                }
            }
        });

        // Roll back the optimistic toggle when the server refuses it.
        builder.addCase(toggleLikeCommunityPost.rejected, (state, action) => {
            const post = state.posts.find((p) => p.id === action.meta.arg);
            if (post) {
                post.isLiked = !post.isLiked;
                post.likes = Math.max(0, post.likes + (post.isLiked ? 1 : -1));
            }
        });

        builder.addCase(toggleSaveCommunityPost.rejected, (state, action) => {
            const post = state.posts.find((p) => p.id === action.meta.arg);
            if (post) post.isSaved = !post.isSaved;
        });

        // Toggle save sync
        builder.addCase(toggleSaveCommunityPost.fulfilled, (state, action) => {
            const { postId, isSaved } = action.payload;
            const post = state.posts.find((p) => p.id === postId);
            if (post) {
                post.isSaved = isSaved;
            }
        });

        // Add comment
        builder
            .addCase(addCommunityComment.pending, (state) => {
                state.commenting = true;
            })
            .addCase(addCommunityComment.fulfilled, (state, action) => {
                state.commenting = false;
                const { postId, comment } = action.payload;
                if (comment) addComment(state, postId, comment);
            })
            .addCase(addCommunityComment.rejected, (state, action) => {
                state.commenting = false;
                state.error = action.payload as string;
            });

        builder.addCase(deleteCommunityComment.fulfilled, (state, action) => {
            removeComment(state, action.payload.postId, action.payload.commentId);
        });

        builder.addCase(deleteCommunityPost.fulfilled, (state, action) => {
            removePost(state, action.payload);
        });
    },
});

export const {
    optimisticToggleLike,
    optimisticToggleSave,
    postReceived,
    postRemoved,
    postLikesChanged,
    commentReceived,
    commentRemoved,
} = communitySlice.actions;
export default communitySlice.reducer;
